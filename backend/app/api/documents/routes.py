from __future__ import annotations

from flask import Blueprint, current_app, request

from app.middleware.auth_middleware import admin_only, current_user
from app.middleware.rate_limit_middleware import rate_limit
from app.middleware.tenant_middleware import assert_owns_entity, assert_tenant_access
from app.services import document_service, kb_service
from app.utils.response_utils import paginated, success, validation_error

bp = Blueprint("documents", __name__, url_prefix="/api/v1")


@bp.get("/upload-config")
@admin_only
def upload_config():
    """Upload limits, so the client can validate a file BEFORE sending it.

    A file over MAX_CONTENT_LENGTH is refused by the server mid-body (413), which
    a browser often surfaces as a bare connection error. Validating client-side
    first lets the UI show an accurate, specific message instead.
    """
    max_bytes = current_app.config["MAX_CONTENT_LENGTH"]
    return success({
        "max_file_size_mb": current_app.config["MAX_UPLOAD_FILE_SIZE_MB"],
        "max_file_size_bytes": max_bytes,
        "allowed_extensions": sorted(current_app.config["ALLOWED_FILE_EXTENSIONS"]),
    })


@bp.post("/knowledge-bases/<kb_id>/documents/upload")
@admin_only
@rate_limit("upload", "RATE_LIMIT_UPLOAD_PER_MINUTE")
def upload_document(kb_id):
    kb = kb_service.get_kb(kb_id)
    assert_owns_entity(current_user(), kb.tenant_id)
    if "file" not in request.files:
        # Diagnose the most common client mistake: a request that isn't proper
        # multipart/form-data (e.g. a boundary-less Content-Type) parses to no
        # files. Log the actual shape so it is obvious in the server logs.
        current_app.logger.warning(
            "upload rejected: no 'file' part. content_type=%r file_keys=%s form_keys=%s",
            request.content_type, list(request.files.keys()), list(request.form.keys()),
        )
        raise validation_error(
            "No file was received. Ensure the file is sent as multipart/form-data "
            "under the field name 'file'."
        )
    file_storage = request.files["file"]
    current_app.logger.info(
        "document upload using existing kb tenant_id=%s kb_id=%s user_id=%s filename=%r",
        kb.tenant_id, kb.id, current_user().id, file_storage.filename,
    )
    doc = document_service.upload_document(kb, file_storage, current_user().id)
    return success(doc.to_dict(), status=201)


@bp.post("/tenants/<tenant_id>/knowledge-bases/documents/upload")
@admin_only
@rate_limit("upload", "RATE_LIMIT_UPLOAD_PER_MINUTE")
def create_kb_and_upload_document(tenant_id):
    user = current_user()
    assert_tenant_access(user, tenant_id)
    if "file" not in request.files:
        raise validation_error(
            "No file was received. Ensure the file is sent as multipart/form-data "
            "under the field name 'file'."
        )
    file_storage = request.files["file"]
    current_app.logger.info(
        "document upload creating new kb tenant_id=%s user_id=%s filename=%r",
        tenant_id, user.id, file_storage.filename,
    )
    kb, doc = document_service.create_kb_and_upload_document(
        tenant_id=tenant_id,
        file_storage=file_storage,
        actor_id=user.id,
        kb_name=request.form.get("kb_name"),
        description=request.form.get("description"),
    )
    return success({
        "knowledge_base": kb_service.kb_payload(kb),
        "document": doc.to_dict(),
    }, status=201)


@bp.get("/knowledge-bases/<kb_id>/documents")
@admin_only
def list_documents(kb_id):
    kb = kb_service.get_kb(kb_id)
    assert_owns_entity(current_user(), kb.tenant_id)
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    items, total = document_service.list_documents(
        kb_id, page, per_page, request.args.get("status"), request.args.get("search")
    )
    return paginated([d.to_dict() for d in items], page, per_page, total)


@bp.get("/documents/<document_id>")
@admin_only
def get_document(document_id):
    doc = document_service.get_document(document_id)
    assert_owns_entity(current_user(), doc.tenant_id)
    return success(doc.to_dict())


@bp.post("/documents/<document_id>/retry")
@admin_only
@rate_limit("upload", "RATE_LIMIT_UPLOAD_PER_MINUTE")
def retry_document(document_id):
    doc = document_service.get_document(document_id)
    assert_owns_entity(current_user(), doc.tenant_id)
    if "file" not in request.files:
        raise validation_error("Re-upload the file to retry ingestion.")
    updated = document_service.retry_document(document_id, request.files["file"], current_user().id)
    return success(updated.to_dict())


@bp.delete("/documents/<document_id>")
@admin_only
def delete_document(document_id):
    doc = document_service.get_document(document_id)
    assert_owns_entity(current_user(), doc.tenant_id)
    kmrag_removed = document_service.delete_document(document_id, current_user().id)
    if kmrag_removed:
        return success({"message": "Document removed and its content deleted from the retrieval engine."})
    return success({
        "message": "Document removed from this knowledge base.",
        "note": "The retrieval engine could not confirm vector removal (it may be offline). "
                "It will be excluded from search; re-run the delete once the engine is back to clean up vectors.",
    })
