from xmonitor.browser.dom.web_helpers import wait_document_ready as _wait_document_ready_impl


def build_support_browser_dom_exports():
    return {
        '_wait_document_ready': _wait_document_ready_impl,
    }
