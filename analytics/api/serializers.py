# analytics/api/serializers.py
"""Plain-Python serializers: Django model instance -> JSON-safe dict."""


def _num(value):
    return float(value) if value is not None else None


def product_to_dict(p):
    boms = list(p.bom_items.all())
    cost = sum(float(b.quantity_per_unit) * float(b.material.unit_cost) for b in boms)
    return {
        "id": p.pk, "code": p.code, "name": p.name, "category": p.category,
        "unit_price": _num(p.unit_price),
        "production_cost": round(cost, 2),
        "profit_margin": round(float(p.unit_price) - cost, 2),
        "bom": [{"material_code": b.material.code, "material": b.material.name,
                 "unit": b.material.unit, "quantity_per_unit": _num(b.quantity_per_unit)} for b in boms],
    }


def material_to_dict(m):
    return {
        "id": m.pk, "code": m.code, "name": m.name, "unit": m.unit,
        "quantity_in_stock": _num(m.quantity_in_stock), "reorder_level": _num(m.reorder_level),
        "unit_cost": _num(m.unit_cost),
        "stock_value": round(float(m.quantity_in_stock) * float(m.unit_cost), 2),
        "low_stock": m.quantity_in_stock <= m.reorder_level,
    }


def employee_to_dict(e):
    # Salaries are deliberately NOT exposed through the API.
    return {
        "id": e.pk, "first_name": e.first_name, "last_name": e.last_name,
        "department": e.department.name if e.department_id else None,
        "is_active": e.is_active, "contract": e.active_contract, "on_leave_today": e.is_on_leave,
        "hire_date": e.hire_date.isoformat() if e.hire_date else None,
    }


def task_to_dict(t):
    return {
        "id": t.pk, "title": t.title,
        "product_code": t.product.code if t.product else None,
        "target_quantity": t.target_quantity, "produced_quantity": t.produced_quantity,
        "progress_percentage": t.progress_percentage, "status": t.status,
        "assigned_to": {"id": t.assigned_to.pk, "name": str(t.assigned_to)} if t.assigned_to else None,
        "due_date": t.due_date.isoformat() if t.due_date else None,
        "is_overdue": t.is_overdue,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def record_to_dict(r):
    return {
        "id": r.pk, "source": r.source,
        "product_code": r.product_code, "product_name": r.product_name, "category": r.category,
        "quantity": r.quantity, "unit_price": _num(r.unit_price),
        "material_cost_per_unit": _num(r.material_cost_per_unit),
        "bom_items": r.bom_items, "bom_qty_per_unit": r.bom_qty_per_unit,
        "standard_days": r.standard_days, "allotted_days": r.allotted_days,
        "artisan_id": r.artisan_id, "artisan_name": r.artisan_name,
        "artisan_contract": r.artisan_contract, "artisan_department": r.artisan_department,
        "dept_match": r.dept_match, "artisan_workload": r.artisan_workload,
        "stock_coverage": r.stock_coverage,
        "start_date": r.start_date.isoformat(), "due_date": r.due_date.isoformat(),
        "end_date": r.end_date.isoformat(), "actual_days": r.actual_days,
        "delayed": r.delayed, "defective_units": r.defective_units,
    }


def order_to_dict(o):
    p = o.prediction or {}
    return {
        "id": o.pk, "reference": o.reference, "customer": o.customer, "channel": o.channel,
        "product_code": o.product_code, "product_name": o.product.name if o.product else None,
        "quantity": o.quantity, "due_date": o.due_date.isoformat(),
        "received_at": o.received_at.isoformat(), "source": o.source, "status": o.status,
        "requested_artisan": str(o.requested_artisan) if o.requested_artisan else None,
        "prediction": {
            "delay_probability": o.delay_probability, "risk_level": o.risk_level,
            "predicted_days": o.predicted_days,
            "predicted_completion": o.predicted_completion.isoformat() if o.predicted_completion else None,
            "expected_delay_days": p.get("expected_delay_days"),
            "recommended_artisan": str(o.recommended_artisan) if o.recommended_artisan else None,
            "stock_ok": o.stock_ok, "shortages": p.get("shortages", []),
            "recommendations": p.get("recommendations", []),
            "model_version": o.model_version,
        },
        "converted_task_id": o.converted_task_id,
    }


def model_version_to_dict(m):
    return {
        "name": m.name, "version": m.version, "algorithm": m.algorithm, "metrics": m.metrics,
        "candidates": m.candidates, "feature_importances": m.feature_importances[:12],
        "n_train": m.n_train, "n_test": m.n_test, "data_source": m.data_source,
        "sklearn_version": m.sklearn_version, "trained_at": m.trained_at.isoformat(),
        "trained_by": m.trained_by, "is_active": m.is_active,
    }
