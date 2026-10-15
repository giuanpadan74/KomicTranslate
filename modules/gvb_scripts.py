def get_js_attach_and_upload_image(temp_path: str) -> str:
    """Restituisce diagnostica stabile su attach/input file di Gemini."""
    escaped = temp_path.replace("\\", "\\\\").replace("'", "\\'")
    return f'''
        (function() {{
            const filePath = '{escaped}';
            const result = {{
                step: 'start',
                attachSelector: null,
                fileInputFound: false,
                fileInputCount: 0,
                filePath: filePath,
                inputAccept: null,
                inputDisabled: null,
                previewFound: false,
                valueSetterExists: false,
                composerFound: false,
                composerClicked: false,
                visibleButtonLabels: [],
                menuTexts: [],
                createImageFound: false,
                error: null
            }};

            try {{
                const composer = document.querySelector('textarea') ||
                                 document.querySelector('[role="textbox"]') ||
                                 document.querySelector('[contenteditable="true"]');
                if (composer) {{
                    result.composerFound = true;
                    if (typeof composer.focus === 'function') {{
                        composer.focus();
                    }}
                    if (typeof composer.click === 'function') {{
                        composer.click();
                        result.composerClicked = true;
                    }}
                }}

                const visibleButtons = Array.from(document.querySelectorAll('button, [role="button"]'))
                    .filter(el => el.offsetParent !== null)
                    .map(el => (el.getAttribute('aria-label') || el.textContent || '').trim())
                    .filter(text => text)
                    .slice(0, 20);
                result.visibleButtonLabels = visibleButtons;

                const attachSelectors = [
                    'button[aria-label="Plus"]',
                    'button[aria-label="Più"]',
                    'button[aria-label="+"]',
                    'button[aria-label*="plus" i]',
                    '[role="button"][aria-label="Plus"]',
                    '[role="button"][aria-label="Più"]',
                    '[role="button"][aria-label="+"]',
                    '[role="button"][aria-label*="plus" i]',
                    'button[aria-label*="attach" i]',
                    'button[aria-label*="aggiungi" i]',
                    'button[aria-label*="allega" i]',
                    '[data-testid="attach-button"]',
                    'button[type="button"][aria-label*="upload" i]',
                    'button[type="button"]',
                    '[role="button"]'
                ];

                for (const sel of attachSelectors) {{
                    const buttons = Array.from(document.querySelectorAll(sel));
                    for (const btn of buttons) {{
                        const label = (btn.getAttribute('aria-label') || btn.textContent || '').trim();
                        const isPlusButton = label === '+' || label.toLowerCase() === 'plus' || label.toLowerCase() === 'più';
                        const isUploadButton = /attach|aggiungi|allega|upload|carica/i.test(label);
                        if (btn.disabled || (!isPlusButton && !isUploadButton && (sel === 'button[type="button"]' || sel === '[role="button"]'))) {{
                            continue;
                        }}
                        btn.click();
                        result.attachSelector = sel + ' => ' + label;
                        result.step = isPlusButton ? 'plus_clicked' : 'attach_clicked';
                        break;
                    }}
                    if (result.attachSelector) {{
                        break;
                    }}
                }}

                const menuCandidates = Array.from(document.querySelectorAll('[role="menuitem"], [role="button"], button, div, li, span'))
                    .map(el => (el.textContent || '').trim())
                    .filter(text => text)
                    .filter(text => /carica file|create image|crea immagine/i.test(text));
                result.menuTexts = menuCandidates.slice(0, 10);
                result.createImageFound = menuCandidates.some(text => /create image|crea immagine/i.test(text));

                const uploadEntry = Array.from(document.querySelectorAll('[role="menuitem"], [role="button"], button, div, li, span'))
                    .find(el => /carica file/i.test((el.textContent || '').trim()));
                if (uploadEntry) {{
                    uploadEntry.click();
                    result.step = 'upload_menu_clicked';
                }}

                const inputs = Array.from(document.querySelectorAll('input[type="file"]'));
                result.fileInputCount = inputs.length;
                const fileInput = inputs.find(el => !el.disabled) || inputs[0] || null;

                if (!fileInput) {{
                    if (result.step === 'upload_menu_clicked') {{
                        result.step = 'upload_menu_clicked_no_input';
                    }} else if (result.attachSelector) {{
                        result.step = 'attach_clicked_no_input';
                    }} else {{
                        result.step = 'no_attach_no_input';
                    }}
                    return JSON.stringify(result);
                }}

                result.fileInputFound = true;
                result.inputAccept = fileInput.getAttribute('accept');
                result.inputDisabled = !!fileInput.disabled;
                result.step = 'file_input_found';

                const descriptor = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
                result.valueSetterExists = !!(descriptor && descriptor.set);

                const preview = document.querySelector('img[src*="blob"], img[src*="data:image"]');
                result.previewFound = !!preview;
                result.step = preview ? 'preview_already_present' : 'file_input_ready';
                return JSON.stringify(result);

            }} catch(e) {{
                result.step = 'exception';
                result.error = String(e && e.message ? e.message : e);
                return JSON.stringify(result);
            }}
        }})();
    '''


def get_js_focus_composer() -> str:
    return '''
        (function() {
            const composer = document.querySelector('textarea') ||
                             document.querySelector('[role="textbox"]') ||
                             document.querySelector('[contenteditable="true"]');
            if (!composer) {
                return JSON.stringify({ found: false, clicked: false, active: false });
            }
            if (typeof composer.focus === 'function') composer.focus();
            if (typeof composer.click === 'function') composer.click();
            const rect = composer.getBoundingClientRect();
            const cx = rect.left + rect.width / 2;
            const cy = rect.top + rect.height / 2;
            composer.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, clientX: cx, clientY: cy }));
            composer.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, clientX: cx, clientY: cy }));
            composer.dispatchEvent(new MouseEvent('click', { bubbles: true, clientX: cx, clientY: cy }));
            return JSON.stringify({
                found: true,
                clicked: true,
                active: document.activeElement === composer,
                tag: composer.tagName,
                ariaLabel: composer.getAttribute('aria-label') || ''
            });
        })();
    '''


def get_js_check_ready_for_input() -> str:
    """Verifica se il campo input è pronto."""
    return '''
        (function() {
            const input = document.querySelector('textarea') ||
                          document.querySelector('[role="textbox"]') ||
                          document.querySelector('[contenteditable="true"]');
            return input !== null && input.getBoundingClientRect().width > 0;
        })();
    '''


def get_js_inject_text(text: str) -> str:
    escaped = text.replace('\\', '\\\\').replace("'", "\\'")
    escaped = escaped.replace('\\n', '\\\\n').replace('\\r', '\\\\r')
    return f'''
        (function() {{
            const input = document.querySelector('textarea') ||
                          document.querySelector('[role="textbox"]') ||
                          document.querySelector('[contenteditable="true"]');
            if (!input) return false;
            
            input.focus();
            const setter = Object.getOwnPropertyDescriptor(
                window.HTMLTextAreaElement.prototype, 'value'
            ).set;
            setter.call(input, '{escaped}');
            input.dispatchEvent(new Event('input', {{ bubbles: true }}));
            return true;
        }})();
    '''


def get_js_is_send_enabled() -> str:
    return '''
        (function() {
            const btn = document.querySelector('button[aria-label*="Invia"]') ||
                        document.querySelector('button[aria-label*="Send"]') ||
                        document.querySelector('button[aria-label*="Run"]') ||
                        document.querySelector('[data-testid="send-button"]') ||
                        document.querySelector('button[type="submit"]');
            if (!btn) {
                return false;
            }
            const visible = btn.offsetParent !== null
                         || (btn.offsetWidth > 0 && btn.offsetHeight > 0)
                         || getComputedStyle(btn).visibility !== 'hidden';
            return !btn.disabled && visible;
        })();
    '''


def get_js_has_image_attachment() -> str:
    return '''
(function() {
    var removeLabels = [
        'Remove file', 'Remove attachment', 'Delete file',
        'Rimuovi file', 'Rimuovi allegato', 'Elimina file',
        'Rimuovi'
    ];
    var allBtns = document.querySelectorAll('button[aria-label]');
    var removeCount = 0;
    for (var bi = 0; bi < allBtns.length; bi++) {
        var b = allBtns[bi];
        var lab = (b.getAttribute('aria-label') || '').toLowerCase();
        var matched = false;
        for (var li = 0; li < removeLabels.length; li++) {
            if (lab.indexOf(removeLabels[li].toLowerCase()) !== -1) {
                matched = true;
                break;
            }
        }
        if (!matched) continue;
        var rect = b.getBoundingClientRect();
        if (b.offsetParent !== null || (rect.width > 0 && rect.height > 0)) {
            removeCount++;
        }
    }
    if (removeCount > 0) {
        return { ok: true, count: removeCount, marker: 'remove_file' };
    }

    var sendBtn = document.querySelector('button[aria-label*="Invia"]') ||
                  document.querySelector('button[aria-label*="Send"]') ||
                  document.querySelector('[data-testid="send-button"]') ||
                  document.querySelector('button[type="submit"]');
    var container = null;
    if (sendBtn) {
        var cur = sendBtn;
        for (var lv = 0; lv < 12 && cur; lv++, cur = cur.parentElement) {
            if (cur.querySelector) {
                var hasTa = !!cur.querySelector('textarea');
                var hasCe = !!cur.querySelector('[contenteditable="true"]');
                var hasTb = !!cur.querySelector('[role="textbox"]');
                if (hasTa || hasCe || hasTb) {
                    container = cur;
                    break;
                }
            }
        }
    }
    var root = container || document.body;
    var imgs = root.querySelectorAll('img');
    var imgCount = 0;
    for (var ii = 0; ii < imgs.length; ii++) {
        var img = imgs[ii];
        var src = img.src || '';
        var box = img.getBoundingClientRect();
        var isBlob = (src.indexOf('blob:') === 0);
        var isData = (src.indexOf('data:image') === 0);
        if (isBlob || isData) {
            if (box.width > 20 && box.height > 20) {
                imgCount++;
            }
        }
    }
    if (imgCount > 0) {
        return {
            ok: true,
            count: imgCount,
            marker: 'image_inside_composer',
            container_found: !!container
        };
    }
    return {
        ok: false,
        count: 0,
        marker: 'none',
        container_found: !!container
    };
})();
'''


def get_js_click_send_button() -> str:
    return '''
        (function() {
            const btn = document.querySelector('button[aria-label*="Invia"]') ||
                        document.querySelector('button[aria-label*="Send"]') ||
                        document.querySelector('button[aria-label*="Run"]') ||
                        document.querySelector('[data-testid="send-button"]') ||
                        document.querySelector('button[type="submit"]');
            if (btn && !btn.disabled && btn.offsetParent !== null) {
                btn.click();
                return true;
            }
            return false;
        })();
    '''


def get_js_is_image_in_input() -> str:
    return '''
        (function() {
            // Cerca immagini caricate nell'input
            const imgs = document.querySelectorAll('img');
            for (const img of imgs) {
                const src = img.src || '';
                if (src.includes('blob') || src.includes('data:image')) {
                    return true;
                }
            }
            
            // Cerca indicatori di upload
            const uploading = document.querySelector('[class*="upload"], [class*="loading"]');
            return uploading !== null;
        })();
    '''
