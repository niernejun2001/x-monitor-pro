DM_PROFILE_BUTTON_SELECTORS = (
    'css:[data-testid="sendDMFromProfile"]',
    'css:[data-testid="sendDM"]',
    'css:button[data-testid="sendDMFromProfile"]',
    'css:button[data-testid="sendDM"]',
    'css:button[aria-label*="私信"]',
    'css:button[aria-label*="发消息"]',
    'css:button[aria-label*="Message"]',
)

DM_EDITOR_SELECTORS = (
    'css:textarea[data-testid="dm-composer-textarea"]',
    'css:textarea[placeholder="Message"]',
    'css:textarea[placeholder*="消息"]',
    'css:[data-testid="dmComposerTextInput"] [contenteditable]:not([contenteditable="false"])',
    'css:[data-testid="dmComposerTextInput"] [contenteditable="true"]',
    'css:div[role="textbox"][contenteditable]:not([contenteditable="false"])',
    'css:div[role="textbox"][contenteditable="true"]',
    'css:[data-testid="dmComposerTextInput"]',
)

DM_SEND_BUTTON_SELECTORS = (
    'css:button[data-testid="dm-composer-send-button"]',
    'css:[data-testid="dm-composer-send-button"]',
    'css:button[data-testid*="dm-composer-send"]',
    'css:[data-testid*="dm-composer-send"]',
    'css:[data-testid="dmComposerSendButton"]',
    'css:button[data-testid="dmComposerSendButton"]',
    'css:button[aria-label*="发送"]',
    'css:button[aria-label*="Send"]',
)

DM_EDITOR_CORE_CSS = (
    'div[role="textbox"][contenteditable="true"]',
    '[data-testid="dmComposerTextInput"] [contenteditable="true"]',
    '[data-testid="dmComposerTextInput"]',
)

DM_CONVERSATION_ROOT_SELECTORS = (
    '[data-testid="DmActivityViewport"]',
    '[data-testid="DmActivityContainer"]',
    'section[role="region"]',
)

