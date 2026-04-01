from xmonitor.services.support.state_payload import build_template_payload
from xmonitor.services.support.template_admin import get_template_list_and_limit


def template_payload(deps):
    return build_template_payload(deps)
