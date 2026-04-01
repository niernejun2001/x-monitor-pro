import json


def set_dep_attr(deps, name, value):
    setter = getattr(deps, '_set_runtime_attr', None)
    if callable(setter):
        return setter(name, value)
    setattr(deps, name, value)
    return value


def write_json_snapshot(path, payload):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=4, ensure_ascii=False)


def load_json_snapshot(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)
