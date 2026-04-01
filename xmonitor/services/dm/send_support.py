def finish_send_success(dom, deps, editor_el, *, confirmed=False, link_only=False, success_text=''):
    cleaned = dom.clear_composer_after_success(editor_el)
    if cleaned:
        if success_text:
            deps.log_headless_debug(success_text)
        return True, ''
    if confirmed or link_only:
        deps.log_to_ui('warn', '⚠️ 私信已确认发送成功，但发送框残留内容；已按成功收口并阻止后续重贴')
        return True, ''
    return False, 'E_DM_POST_SEND_DIRTY_COMPOSER: 私信已发送但输入框仍残留内容'


def confirm_send_result(
    *,
    tab,
    dom,
    deps,
    editor_el,
    before_counts,
    probes,
    dm_text,
    link_only_mode,
    success_text='',
    uncleared_error='点击私信发送后输入框未清空',
    cleared_unconfirmed_error='文本私信输入框已清空，但未确认消息落库',
):
    confirmed = deps._confirm_dm_message_sent(
        tab,
        before_counts,
        probes,
        wait_sec=max(
            deps.DM_SEND_CONFIRM_WAIT_SEC,
            1.8 if not link_only_mode else deps.DM_SEND_CONFIRM_WAIT_SEC,
        ),
        message_text=dm_text,
    )
    if dom.composer_cleared(editor_el):
        if link_only_mode:
            return finish_send_success(dom, deps, editor_el, confirmed=confirmed, link_only=True)
        if confirmed:
            return finish_send_success(dom, deps, editor_el, confirmed=True, success_text=success_text)
        return False, cleared_unconfirmed_error
    if confirmed:
        return finish_send_success(dom, deps, editor_el, confirmed=True, success_text=success_text)
    return False, uncleared_error


def ensure_editor_text_stable(tab, editor, dm_text, link_only_mode, deps, dom):
    if dom.editor_has_text(editor, dm_text):
        return True, ''
    if link_only_mode:
        deps._poke_dm_editor_events(tab, editor)
        if dom.editor_has_text(editor, dm_text):
            return True, ''
        deps._dm_humanized_idle(tab, 0.08, 0.2, '链接输入校验失败后等待')
        return False, '输入后链接状态未稳定写入编辑器'

    deps._dm_humanized_idle(tab, 0.04, 0.12, '私信文本二次回填前')
    recovered = dom.force_fill_dm_editor_text(editor, dm_text)
    if not recovered and not dom.editor_has_text(editor, dm_text):
        recovered = deps._humanized_type_dm_text(tab, editor, dm_text)
    if recovered or dom.editor_has_text(editor, dm_text):
        return True, ''
    deps._dm_humanized_idle(tab, 0.08, 0.2, '私信输入校验失败后等待')
    return False, '输入后文本未稳定写入编辑器'


def attempt_send_via_button(tab, editor, dm_text, link_only_mode, deps, dom, before_counts, probes):
    send_btn = dom.wait_send_button_after_input(editor, dm_text, link_mode=link_only_mode)
    if not send_btn:
        return None, ''
    clicked_send, click_err = deps._click_with_prompt_guard(tab, send_btn, '点击私信发送按钮')
    if not clicked_send:
        return False, f'E_DM_SEND_BUTTON_CLICK: {click_err}'
    deps._dm_humanized_idle(tab, 0.06, 0.16, '私信发送后确认')
    return confirm_send_result(
        tab=tab,
        dom=dom,
        deps=deps,
        editor_el=editor,
        before_counts=before_counts,
        probes=probes,
        dm_text=dm_text,
        link_only_mode=link_only_mode,
        success_text='私信发送后已确认消息落库，已清理发送框后按成功处理',
        uncleared_error='点击私信发送后输入框未清空',
        cleared_unconfirmed_error='文本私信输入框已清空，但未确认消息落库',
    )


def attempt_send_via_enter(tab, editor, dm_text, link_only_mode, deps, dom, before_counts, probes):
    if not dom.editor_has_text(editor, dm_text):
        return None, ''
    deps._dm_humanized_idle(tab, 0.02, 0.08, '私信发送Enter兜底前')
    try:
        enter_sent = bool(tab.run_js(
            """
            const el = arguments[0];
            if (!el) return false;
            try { el.focus(); } catch (e) {}
            const ev = { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true };
            try { el.dispatchEvent(new KeyboardEvent('keydown', ev)); } catch (e) {}
            try { el.dispatchEvent(new KeyboardEvent('keypress', ev)); } catch (e) {}
            try { el.dispatchEvent(new KeyboardEvent('keyup', ev)); } catch (e) {}
            return true;
            """,
            editor,
        ))
    except Exception:
        enter_sent = False
    if not enter_sent:
        return False, '发送按钮未出现或未激活，且Enter兜底未确认发送'
    deps._dm_humanized_idle(tab, 0.06, 0.16, '私信发送Enter兜底后')
    return confirm_send_result(
        tab=tab,
        dom=dom,
        deps=deps,
        editor_el=editor,
        before_counts=before_counts,
        probes=probes,
        dm_text=dm_text,
        link_only_mode=link_only_mode,
        success_text='私信Enter兜底后已确认消息落库，已清理发送框后按成功处理',
        uncleared_error='发送按钮未出现或未激活，且Enter兜底未确认发送',
        cleared_unconfirmed_error='文本私信Enter后输入框已清空，但未确认消息落库',
    )


def attempt_send_via_dom(tab, editor, dm_text, link_only_mode, deps, dom, before_counts, probes):
    deps._dm_humanized_idle(tab, 0.06, 0.18, '私信发送DOM兜底前')
    try:
        clicked = tab.run_js(
            """
            const selectors = [
              'button[data-testid="dm-composer-send-button"]',
              '[data-testid="dm-composer-send-button"]',
              'button[data-testid*="dm-composer-send"]',
              '[data-testid*="dm-composer-send"]',
              '[data-testid="dmComposerSendButton"]',
              'button[data-testid="dmComposerSendButton"]',
              'button[aria-label*="Send"]',
              'button[aria-label*="发送"]',
              '[role="button"][aria-label*="Send"]',
              '[role="button"][aria-label*="发送"]',
            ];
            for (const s of selectors) {
              const nodes = Array.from(document.querySelectorAll(s));
              for (const el of nodes) {
                const style = window.getComputedStyle(el);
                const hidden = style.display === 'none' || style.visibility === 'hidden';
                const disabled = el.disabled || el.getAttribute('aria-disabled') === 'true';
                if (!hidden && !disabled) {
                  el.click();
                  return true;
                }
              }
            }
            return false;
            """
        )
        if not clicked:
            return None, ''
        deps._dm_humanized_idle(tab, 0.06, 0.16, '私信发送DOM兜底后')
        return confirm_send_result(
            tab=tab,
            dom=dom,
            deps=deps,
            editor_el=editor,
            before_counts=before_counts,
            probes=probes,
            dm_text=dm_text,
            link_only_mode=link_only_mode,
            success_text='DOM发送后已确认消息落库，已清理发送框后按成功处理',
            uncleared_error='DOM点击发送后输入框未清空',
            cleared_unconfirmed_error='DOM文本发送后输入框已清空，但未确认消息落库',
        )
    except Exception:
        return None, ''
