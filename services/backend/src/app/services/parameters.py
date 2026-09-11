from __future__ import annotations

import math
from collections.abc import Mapping


def validate_against_schema(
    schema: Mapping[str, object],
    value: object,
    path: str = "parameters",
) -> list[tuple[str, str]]:
    """校验 value 是否符合 parameterSchema（JSON Schema 子集）。

    支持关键字：type / required / additionalProperties / properties /
    minimum / maximum / enum。返回 [(字段路径, 错误描述)]，空表示通过。
    结构约束以策略 info() 暴露的 schema 为唯一来源，保证与 /strategies
    接口（前端构造参数的依据）一致。
    """
    errors: list[tuple[str, str]] = []
    schema_type = schema.get("type")

    if schema_type == "object":
        if not isinstance(value, dict):
            return [(path, "必须是对象")]
        properties = schema.get("properties", {})
        for key, sub_schema in properties.items():
            if key in value:
                errors.extend(validate_against_schema(sub_schema, value[key], f"{path}.{key}"))
        unknown = set(value) - set(properties)
        if unknown and schema.get("additionalProperties", True) is False:
            errors.append((f"{path}.{sorted(unknown)[0]}", "未知字段"))
        for key in schema.get("required", []):
            if key not in value:
                errors.append((f"{path}.{key}", "缺少必填字段"))
        return errors

    if not _matches_type(value, schema_type):
        errors.append((path, f"必须是 {schema_type} 类型"))

    if isinstance(value, float) and not math.isfinite(value):
        errors.append((path, "必须是有限数值"))

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(schema.get("minimum"), (int, float)) and value < schema["minimum"]:
            errors.append((path, f"不能小于 {schema['minimum']}"))
        if isinstance(schema.get("maximum"), (int, float)) and value > schema["maximum"]:
            errors.append((path, f"不能大于 {schema['maximum']}"))

    if "enum" in schema and value not in schema["enum"]:
        errors.append((path, f"必须是 {schema['enum']} 之一"))

    return errors


def _matches_type(value: object, schema_type: object) -> bool:
    """JSON 语义的类型检查：bool 不是 integer/number。"""
    if schema_type == "string":
        return isinstance(value, str)
    if schema_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if schema_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if schema_type == "boolean":
        return isinstance(value, bool)
    return True
