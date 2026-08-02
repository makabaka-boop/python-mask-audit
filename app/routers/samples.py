"""样例文本路由。"""
from flask import Blueprint, jsonify, request

from ..errors import ValidationError
from ..repositories import AuditRepository, SampleRepository

samples_bp = Blueprint("samples", __name__, url_prefix="/api/v1/samples")


def _repo() -> SampleRepository:
    return SampleRepository()


def _audit() -> AuditRepository:
    return AuditRepository()


@samples_bp.get("")
def list_samples():
    category = request.args.get("category")
    samples = _repo().list(category=category)
    return jsonify({"items": samples, "total": len(samples)})


@samples_bp.post("")
def create_sample():
    payload = request.get_json(silent=True) or {}
    sample_name = payload.get("sample_name")
    raw_text = payload.get("raw_text")
    if not sample_name or not isinstance(sample_name, str):
        raise ValidationError(
            "sample_name 不能为空", details={"field": "sample_name"}
        )
    if raw_text is None or not isinstance(raw_text, str):
        raise ValidationError("raw_text 不能为空", details={"field": "raw_text"})
    sample_category = payload.get("sample_category")
    expected_note = payload.get("expected_note")
    sample = _repo().create(
        sample_name=sample_name,
        raw_text=raw_text,
        sample_category=sample_category,
        expected_note=expected_note,
    )
    _audit().record(
        event_type="sample_created",
        entity_type="sample",
        entity_id=sample["id"],
        detail={"sample_name": sample_name},
    )
    return jsonify(sample), 201


@samples_bp.get("/<int:sample_id>")
def get_sample(sample_id: int):
    return jsonify(_repo().get_by_id(sample_id))


@samples_bp.delete("/<int:sample_id>")
def delete_sample(sample_id: int):
    _repo().delete(sample_id)
    _audit().record(
        event_type="sample_deleted", entity_type="sample", entity_id=sample_id
    )
    return jsonify({"deleted": True, "sample_id": sample_id})
