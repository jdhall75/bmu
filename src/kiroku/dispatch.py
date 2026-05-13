"""Fire a Job against its devices, creating a RunBatch + Run rows and publishing specs."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from kiroku.jobs import CredentialRef, JobSpec
from kiroku.models import Credential, Device, DeviceGroup, Job, Run, RunBatch, RunStatus
from kiroku.queue import publish_job


def _spec_for(
    device: Device,
    job: Job,
    run: Run,
    schedule_id: int | None,
    *,
    group: DeviceGroup | None = None,
    default_cred: Credential | None = None,
) -> JobSpec | None:
    cred = (
        device.credential
        or (group.default_credential if group else None)
        or default_cred
    )
    if cred is None:
        return None

    parser = job.parser_template
    custom_yaml = (
        device.custom_platform.yaml_body
        if device.custom_platform_id and device.custom_platform
        else None
    )
    return JobSpec(
        run_id=run.id,
        schedule_id=schedule_id,
        device_id=device.id,
        device_name=device.name,
        hostname=device.hostname,
        port=device.port,
        kind=job.kind.value,
        job_id=job.id,
        driver_kind=device.driver_kind.value if device.driver_kind else "cli",
        platform=device.platform if not custom_yaml else None,
        custom_platform_yaml=custom_yaml,
        transport=device.transport.value if device.transport else None,
        commands=[c.strip() for c in (job.commands or "").splitlines() if c.strip()],
        rpc=job.rpc,
        parser_template_id=parser.id if parser else None,
        parser_type=parser.type.value if parser else None,
        parser_body=parser.body if parser else None,
        cve_vendor=job.cve_vendor,
        cve_product=job.cve_product,
        connect_timeout=device.connect_timeout,
        command_timeout=device.command_timeout,
        credential=CredentialRef(
            provider=cred.provider.value,
            credential_id=cred.id,
            ref=cred.ref,
        ),
    )


def fire_job(
    job: Job,
    db: Session,
    *,
    schedule_id: int | None = None,
    schedule_name: str | None = None,
    commit: bool = True,
) -> RunBatch:
    """Create a RunBatch, queue specs for all enabled devices, and return the batch."""
    now = datetime.now(tz=timezone.utc)

    default_cred: Credential | None = db.scalar(
        select(Credential).where(Credential.is_default.is_(True))
    )

    seen: set[int] = set()
    # Track (device, targeting_group) so credential fallback uses the right group.
    device_group_pairs: list[tuple[Device, DeviceGroup | None]] = []

    for group in job.device_groups:
        for d in group.devices:
            if d.enabled and d.id not in seen:
                seen.add(d.id)
                device_group_pairs.append((d, group))

    for d in job.devices:
        if d.enabled and d.id not in seen:
            seen.add(d.id)
            device_group_pairs.append((d, None))

    batch = RunBatch(
        schedule_id=schedule_id,
        schedule_name=schedule_name or job.name,
        kind=job.kind.value,
        total=len(device_group_pairs),
        started_at=now,
    )
    db.add(batch)
    db.flush()

    pairs: list[tuple[Device, DeviceGroup | None, Run]] = []
    for device, group in device_group_pairs:
        run = Run(
            schedule_id=schedule_id,
            batch_id=batch.id,
            device_id=device.id,
            kind=job.kind.value,
            status=RunStatus.PENDING,
        )
        db.add(run)
        pairs.append((device, group, run))
    db.flush()

    for device, group, run in pairs:
        spec = _spec_for(
            device, job, run, schedule_id, group=group, default_cred=default_cred
        )
        if spec is None:
            run.status = RunStatus.FAILED
            run.error = "no credential available"
            run.finished_at = now
            batch.failed += 1
            continue
        publish_job(spec)

    if commit:
        db.commit()
    return batch
