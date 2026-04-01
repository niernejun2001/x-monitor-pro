import time


def wait_document_ready(tab, timeout=5.0):
    deadline = time.time() + max(0.3, float(timeout))
    while time.time() < deadline:
        try:
            ready = str(tab.run_js("return document.readyState || ''") or '').lower()
            if ready in {'interactive', 'complete'}:
                return True
        except Exception:
            pass
        time.sleep(0.08)
    return False


def is_element_actionable(ele):
    if not ele:
        return False
    try:
        if not ele.states.is_displayed:
            return False
    except Exception:
        return False
    try:
        aria_disabled = (ele.attr('aria-disabled') or '').strip().lower() == 'true'
        html_disabled = ele.attr('disabled') is not None
        if aria_disabled or html_disabled:
            return False
    except Exception:
        pass
    return True


def wait_first_actionable(tab, selectors, timeout=2.5, poll=0.12):
    deadline = time.time() + max(0.2, float(timeout))
    while time.time() < deadline:
        for selector in selectors:
            try:
                cands = tab.eles(selector, timeout=0.35)
            except Exception:
                cands = []
            for cand in cands:
                if is_element_actionable(cand):
                    return cand
        time.sleep(max(0.04, float(poll)))
    return None


def wait_first_visible(tab, selectors, timeout=3.0, poll=0.12):
    deadline = time.time() + max(0.2, float(timeout))
    while time.time() < deadline:
        for selector in selectors:
            try:
                cand = tab.ele(selector, timeout=0)
            except Exception:
                cand = None
            try:
                if cand and cand.states.is_displayed:
                    return cand
            except Exception:
                continue
        time.sleep(poll)
    return None
