"""Celery tasks: take over the Community plugin's photo albums."""

from __future__ import annotations

from hubra.core.modules import per_tenant_job
from hubra.core.tasks import celery_app


@celery_app.task(name="hubra_documents.tasks.take_over_albums")
@per_tenant_job("documents")
def take_over_albums() -> dict:
    from hubra.core.extensions import db

    from .takeover import take_over_albums as run

    done = run()
    db.session.commit()
    return done
