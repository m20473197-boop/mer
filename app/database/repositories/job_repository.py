"""Repository for Job model."""

from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.job import Job


class JobRepository:
    """Database access for ``jobs`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Reads -----------------------------------------------------------

    async def get_by_id(self, job_id: int) -> Job | None:
        return await self._session.get(Job, job_id)

    async def get_by_name(self, name: str) -> Job | None:
        stmt = select(Job).where(Job.name == name)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_active(self) -> list[Job]:
        stmt = (
            select(Job)
            .where(Job.is_active.is_(True))
            .order_by(Job.required_level, Job.hourly_salary)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_all(self) -> list[Job]:
        stmt = select(Job).order_by(Job.required_level, Job.hourly_salary)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(self) -> int:
        stmt = select(Job.id)
        result = await self._session.execute(stmt)
        return len(result.scalars().all())

    async def update_fields(self, job_id: int, **fields: object) -> bool:
        """Update a whitelisted set of job settings (admin panel)."""
        allowed = {
            "description",
            "salary",
            "hourly_salary",
            "employer",
            "cooldown",
            "required_level",
            "is_active",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"unknown job attributes: {sorted(unknown)}")
        if not fields:
            return False
        statement = update(Job).where(Job.id == job_id).values(**fields)
        result = await self._session.execute(
            statement, execution_options={"synchronize_session": False}
        )
        cached = await self._session.get(Job, job_id)
        if cached is not None:
            self._session.expire(cached)
        return bool(result.rowcount)

    # --- Writes ----------------------------------------------------------

    def add(self, job: Job) -> None:
        self._session.add(job)

    async def create_job(
        self,
        name: str,
        description: str,
        salary: int,
        cooldown: int,
        required_level: int,
        required_skill: str | None = None,
        is_active: bool = True,
        hourly_salary: int | None = None,
        employer: str = "",
    ) -> Job:
        job = Job(
            name=name,
            description=description,
            salary=salary,
            hourly_salary=hourly_salary if hourly_salary is not None else salary,
            employer=employer,
            cooldown=cooldown,
            required_level=required_level,
            required_skill=required_skill,
            is_active=is_active,
        )
        self._session.add(job)
        await self._session.flush()
        return job

    async def ensure_initial_jobs(self) -> list[Job]:
        """Seed the «خر حمالی» catalog and retire the old jobs.

        Idempotent and safe on every boot:

        * a missing job is created with the catalog values;
        * an existing job is **never** overwritten, except for the historical
          backfill of the columns the time-based salary update added (an admin
          edit of salary/level/employer therefore survives restarts);
        * the jobs that used to be selectable but are not part of the catalog
          any more are *deactivated*, never deleted — their rows, their
          earnings history and anyone currently working there all survive, the
          job simply stops being offerable.
        """
        from app.core import constants

        c = constants
        initial_jobs = [
            {
                "name": c.JOB_MASON_NAME,
                "description": c.JOB_MASON_DESCRIPTION,
                "salary": c.JOB_MASON_SALARY,
                "hourly_salary": c.JOB_MASON_HOURLY_SALARY,
                "employer": c.JOB_MASON_EMPLOYER,
                "cooldown": c.JOB_MASON_COOLDOWN,
                "required_level": c.JOB_MASON_REQUIRED_LEVEL,
            },
            {
                "name": c.JOB_RESTAURANT_NAME,
                "description": c.JOB_RESTAURANT_DESCRIPTION,
                "salary": c.JOB_RESTAURANT_SALARY,
                "hourly_salary": c.JOB_RESTAURANT_HOURLY_SALARY,
                "employer": c.JOB_RESTAURANT_EMPLOYER,
                "cooldown": c.JOB_RESTAURANT_COOLDOWN,
                "required_level": c.JOB_RESTAURANT_REQUIRED_LEVEL,
            },
            {
                "name": c.JOB_SALES_NAME,
                "description": c.JOB_SALES_DESCRIPTION,
                "salary": c.JOB_SALES_SALARY,
                "hourly_salary": c.JOB_SALES_HOURLY_SALARY,
                "employer": c.JOB_SALES_EMPLOYER,
                "cooldown": c.JOB_SALES_COOLDOWN,
                "required_level": c.JOB_SALES_REQUIRED_LEVEL,
            },
            {
                "name": c.JOB_COURIER_NAME,
                "description": c.JOB_COURIER_DESCRIPTION,
                "salary": c.JOB_COURIER_SALARY,
                "hourly_salary": c.JOB_COURIER_HOURLY_SALARY,
                "employer": c.JOB_COURIER_EMPLOYER,
                "cooldown": c.JOB_COURIER_COOLDOWN,
                "required_level": c.JOB_COURIER_REQUIRED_LEVEL,
            },
            {
                "name": c.JOB_SNAPP_NAME,
                "description": c.JOB_SNAPP_DESCRIPTION,
                "salary": c.JOB_SNAPP_SALARY,
                "hourly_salary": c.JOB_SNAPP_HOURLY_SALARY,
                "employer": c.JOB_SNAPP_EMPLOYER,
                "cooldown": c.JOB_SNAPP_COOLDOWN,
                "required_level": c.JOB_SNAPP_REQUIRED_LEVEL,
            },
            {
                "name": c.JOB_BANK_CLERK_NAME,
                "description": c.JOB_BANK_CLERK_DESCRIPTION,
                "salary": c.JOB_BANK_CLERK_SALARY,
                "hourly_salary": c.JOB_BANK_CLERK_HOURLY_SALARY,
                "employer": c.JOB_BANK_CLERK_EMPLOYER,
                "cooldown": c.JOB_BANK_CLERK_COOLDOWN,
                "required_level": c.JOB_BANK_CLERK_REQUIRED_LEVEL,
            },
        ]

        existing = await self.list_all()
        existing_by_name = {job.name: job for job in existing}
        catalog_names = {job_data["name"] for job_data in initial_jobs}

        for job_data in initial_jobs:
            job = existing_by_name.get(job_data["name"])
            if job is None:
                await self.create_job(**job_data)
                continue
            # Backfill fields added by the time-based salary update on jobs
            # that already existed in an older database.
            changed = False
            if not job.employer and job_data.get("employer"):
                job.employer = job_data["employer"]
                changed = True
            if job.hourly_salary == 0 and job_data.get("hourly_salary"):
                job.hourly_salary = job_data["hourly_salary"]
                changed = True
            if changed:
                self._session.add(job)

        await self.retire_legacy_jobs(catalog_names)
        await self._session.flush()
        return await self.list_active()

    async def retire_legacy_jobs(self, keep_names: set[str] | None = None) -> int:
        """Deactivate the jobs the old catalog offered but the new one drops.

        Only ``constants.JOB_LEGACY_RETIRED_NAMES`` are touched, so jobs an
        admin created from the panel are never switched off by this. Before a
        row is switched off it gets the same salary/employer backfill the
        catalog rows get, so a player who is still working there is paid at the
        rate they were hired for instead of zero. Returns how many rows were
        deactivated (0 on every boot after the first).
        """
        from app.core import constants

        retired = 0
        for name, (hourly_salary, employer) in constants.JOB_LEGACY_COMPAT.items():
            if keep_names and name in keep_names:
                continue  # still part of the catalog after all
            job = await self.get_by_name(name)
            if job is None:
                continue
            if job.hourly_salary == 0:
                await self.update_fields(
                    job.id, hourly_salary=hourly_salary, employer=employer
                )
                job = await self.get_by_name(name)
            if job is not None and job.is_active:
                await self.update_fields(job.id, is_active=False)
                retired += 1
        return retired
