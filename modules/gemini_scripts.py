import json

def get_js_check_ready() -> str:
    """Check if the Gemini input area is ready."""
    return '''
        (function() {
            const input = document.querySelector('textarea') || 
                        document.querySelector('[role="textbox"]') ||
                        document.querySelector('.ql-editor') ||
                        document.querySelector('div[contenteditable="true"]');
            
            // Verifica se il campo è visibile e pronto
            return input !== null && input.getBoundingClientRect().width > 0;
        })();
    '''

def get_js_inject(js_text_string: str) -> str:
    """Inject the prompt into the Gemini input area."""
    return f'''
        (function() {{
            const input = document.querySelector('textarea') ||
                        document.querySelector('[role="textbox"]') ||
                        document.querySelector('.ql-editor') ||
                        document.querySelector('div[contenteditable="true"]');

            if (input) {{
                input.focus();

                const fullText = {js_text_string};
                if (input.tagName === 'TEXTAREA') {{
                    input.value = fullText;
                }} else {{
                    document.execCommand('selectAll', false, null);
                    document.execCommand('delete', false, null);
                    const textNode = document.createTextNode(fullText);
                    input.appendChild(textNode);
                }}

                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                input.dispatchEvent(new Event('change', {{ bubbles: true }}));

                setTimeout(() => {{ input.focus(); }}, 100);
                return true;
            }}
            return false;
        }})();
    '''

def get_js_verify_input() -> str:
    """Verify that text was entered in the input area."""
    return '''
        (function() {
            const input = document.querySelector('textarea') ||
                        document.querySelector('[role="textbox"]') ||
                        document.querySelector('.ql-editor') ||
                        document.querySelector('div[contenteditable="true"]');

            if (!input) return false;

            if (input.tagName === 'TEXTAREA') {
                return input.value.length > 0;
            }
            return input.innerText.trim().length > 0;
        })();
    '''

def get_js_wait_for_send_button() -> str:
    """Try to find and click the Send button once. Returns true if clicked, false if not found.

    Il selettore cerca il bottone SOLO all'interno dello stesso container del campo
    di input, per evitare di matchare pulsanti ambigui presenti nella sidebar
    (es. voci del menu contestuale delle chat come "Condividi conversazione").
    Inoltre privilegia il selettore basato sull'icona material (svgicon="send"),
    che è univoco per il pulsante di invio, rispetto agli aria-label testuali
    che possono variare o collidere con altri bottoni della pagina.
    """
    return '''
        (function() {
            function isUsable(btn) {
                return btn && !btn.disabled && btn.offsetParent !== null;
            }

            function findInput() {
                return document.querySelector('textarea') ||
                       document.querySelector('[role="textbox"]') ||
                       document.querySelector('.ql-editor') ||
                       document.querySelector('div[contenteditable="true"]');
            }

            function findSendButtonNearInput() {
                const input = findInput();
                if (!input) return null;

                // Risali l'albero dal input per trovare il container del composer
                // che ospita anche il pulsante Invia.
                let container = input.parentElement;
                for (let i = 0; i < 6 && container; i++) {
                    // 1) Selettore più affidabile: icona send dentro un <button>
                    let btn = container.querySelector('button:has(mat-icon[svgicon="send"])');
                    if (!btn) {
                        const icon = container.querySelector('mat-icon[svgicon="send"]');
                        if (icon) btn = icon.closest('button');
                    }
                    if (isUsable(btn)) return btn;

                    // 2) Fallback: aria-label del pulsante, ma solo nel container
                    btn = container.querySelector('button[aria-label*="Invia"]') ||
                          container.querySelector('button[aria-label*="Send"]') ||
                          container.querySelector('button[aria-label*="Run"]');
                    if (isUsable(btn)) return btn;

                    container = container.parentElement;
                }
                return null;
            }

            const sendBtn = findSendButtonNearInput();
            if (sendBtn) {
                console.log('[GeminiAuto] Pulsante invio trovato e attivo!');
                sendBtn.click();
                return true;
            }
            console.log('[GeminiAuto] Pulsante invio non disponibile al momento.');
            return false;
        })();
    '''

def get_js_extract(expected_count: int) -> str:
    """Extract the JSON response from the Gemini page."""
    return f'''
        (function() {{
            const expectedCount = {expected_count};
            
            function isGenerationFinished() {{
                // Funzione helper per trovare il pulsante copia (comune a più logiche)
                function hasCopyButton() {{
                    const copySelectors = [
                        'button[aria-label*="Copia risposta"]',
                        'button[aria-label*="Copy response"]',
                        'button[aria-label*="Copia"]',
                        'button[aria-label*="Copy"]',
                        '[data-testid*="copy-button"]',
                        'button:has(mat-icon[svgicon*="copy"])',
                        'button:has(mat-icon[svgicon*="content_copy"])',
                        'mat-icon[svgicon*="copy"]',
                        'mat-icon[svgicon*="content_copy"]'
                    ];
                    for (let s of copySelectors) {{
                        let el = document.querySelector(s);
                        if (el && el.offsetParent !== null) return true;
                    }}
                    // Cerca tra tutti i bottoni per testo nell'aria-label
                    return Array.from(document.querySelectorAll('button')).some(b => {{
                        const label = (b.getAttribute('aria-label') || '').toLowerCase();
                        return (label.includes('copia') || label.includes('copy')) && b.offsetParent !== null;
                    }});
                }}

                // Simboli di feedback (indicano che la generazione è finita)
                const feedbackIcons = document.querySelector('button[aria-label*="Buona risposta"]') ||
                                   document.querySelector('button[aria-label*="Good response"]') ||
                                   document.querySelector('[data-testid="thumbs-up-button"]') ||
                                   document.querySelector('mat-icon[svgicon*="thumb_up"]');

                const stopBtn = document.querySelector('button[aria-label*="Interrompi"]') ||
                               document.querySelector('button[aria-label*="Stop"]');
                
                const sendBtn = document.querySelector('button[aria-label*="Invia"]') ||
                               document.querySelector('button[aria-label*="Send"]');

                // Se c'è il pulsante Copia o i pollici, è finita. 
                // Se il pulsante Invia è attivo e quello Stop è sparito, è finita.
                return hasCopyButton() || feedbackIcons !== null || (sendBtn && !sendBtn.disabled && !stopBtn);
            }}

            if (!isGenerationFinished()) return "NOT_FINISHED";

            function isCompleteResult(parsed) {{
                if (!parsed || typeof parsed !== 'object') return false;
                const keys = Object.keys(parsed).filter(k => /^block_\\d+$/.test(k));
                if (!keys.length) return false;
                if (expectedCount <= 0) return true;
                for (let i = 1; i <= expectedCount; i++) {{
                    const value = parsed[`block_${{i}}`];
                    if (typeof value !== 'string' || !value.trim()) return false;
                }}
                return true;
            }}

            function extractJson(text) {{
                if (!text) return null;
                const startIdx = text.indexOf('{{');
                const endIdx = text.lastIndexOf('}}');
                if (startIdx !== -1 && endIdx !== -1 && endIdx > startIdx) {{
                    const possibleJson = text.substring(startIdx, endIdx + 1);
                    if (possibleJson.includes('"block_1"')) {{
                        return possibleJson;
                    }}
                }}
                return null;
            }}

            function extractStructuredBlocks(text) {{
                if (!text || !text.includes('block_1')) return null;
                const blocks = {{}};
                const regex = /"?block_(\\d+)"?\\s*[:=]\\s*"([\\s\\S]*?)(?="\\s*,\\s*"block_\\d+"\\s*:|"$|\\n\\s*"?block_\\d+"?\\s*[:=]|\\n\\s*}}|\\s*}}\\s*$)/g;
                let match;
                while ((match = regex.exec(text)) !== null) {{
                    const value = match[2]
                        .replace(/\\\\n/g, '\\n')
                        .replace(/\\\\r/g, '\\r')
                        .replace(/\\\\t/g, '\\t')
                        .replace(/\\"/g, '"')
                        .replace(/\\\\\\\\/g, '\\\\')
                        .trim();
                    blocks[`block_${{match[1]}}`] = value;
                }}
                return Object.keys(blocks).length ? JSON.stringify(blocks) : null;
            }}

            function parsePlainBlocks(text) {{
                if (!text || !text.includes('block_1')) return null;
                const blocks = {{}};
                const regex = /"?block_(\\d+)"?\\s*[:=]\\s*["']?(.+?)["']?(?:,?$)/gm;
                let match;
                while ((match = regex.exec(text)) !== null) {{
                    blocks[`block_${{match[1]}}`] = match[2].trim();
                }}
                return Object.keys(blocks).length ? JSON.stringify(blocks) : null;
            }}

            // Cerca nei blocchi di codice
            let resultData = null;
            const codeBlocks = document.querySelectorAll('pre, code, .code-block-body');
            for (const block of codeBlocks) {{
                resultData = extractJson(block.innerText);
                if (resultData) break;
            }}

            // Cerca nei contenitori di risposta se non trovato
            if (!resultData) {{
                const selectors = ['.message-content', '[data-testid="response-container"]', '.markdown'];
                for (const selector of selectors) {{
                    const elements = document.querySelectorAll(selector);
                    if (elements.length > 0) {{
                        const lastText = elements[elements.length - 1].innerText;
                        resultData = extractJson(lastText) || extractStructuredBlocks(lastText) || parsePlainBlocks(lastText);
                        if (resultData) break;
                    }}
                }}
            }}

            // Validazione finale: verifica che tutti i blocchi siano presenti e non vuoti
            if (resultData) {{
                try {{
                    const parsed = JSON.parse(resultData);
                    if (!isCompleteResult(parsed)) {{
                        const keys = Object.keys(parsed).filter(k => k.startsWith('block_'));
                        console.log('[GeminiAuto] Validazione fallita: trovati ' + keys.length + '/' + expectedCount);
                        return "INCOMPLETE_JSON"; // Trovato ma non tutto
                    }}
                    return resultData;
                }} catch (e) {{
                    return "INVALID_JSON";
                }}
            }}

            return "JSON_NOT_FOUND";
        }})();
    '''

def get_js_consent() -> str:
    """Handle Google consent page."""
    return '''
        (function() {
            const btn = Array.from(document.querySelectorAll('button')).find(b => 
                b.innerText.includes('Accetta tutto') || b.innerText.includes('Accept all'));
            if (btn) btn.click();
        })();
    '''

def get_js_copy_response() -> str:
    """Find and click the Copy button to copy the response."""
    return '''
        (function() {
            function findCopyButton() {
                const selectors = [
                    'button[aria-label*="Copia risposta"]',
                    'button[aria-label*="Copy response"]',
                    'button[aria-label*="Copia"]',
                    'button[aria-label*="Copy"]',
                    '[data-testid*="copy-button"]',
                    'button:has(mat-icon[svgicon*="copy"])',
                    'button:has(mat-icon[svgicon*="content_copy"])',
                    'mat-icon[svgicon*="copy"]',
                    'mat-icon[svgicon*="content_copy"]'
                ];

                for (let selector of selectors) {
                    let el = document.querySelector(selector);
                    if (el) {
                        if (el.tagName === 'MAT-ICON') el = el.closest('button');
                        if (el && !el.disabled && el.offsetParent !== null) return el;
                    }
                }
                
                return Array.from(document.querySelectorAll('button')).find(b => {
                    const label = (b.getAttribute('aria-label') || '').toLowerCase();
                    return (label.includes('copia') || label.includes('copy')) && !b.disabled && b.offsetParent !== null;
                });
            }

            const copyBtn = findCopyButton();
            if (copyBtn) {
                console.log('[GeminiAuto] Pulsante Copia trovato. Provo il click...');
                
                // Tenta diversi metodi di click per massimizzare la compatibilità
                try {
                    copyBtn.click();
                } catch(e) { console.log('Click standard fallito'); }
                
                try {
                    const clickEvent = new MouseEvent('click', {
                        bubbles: true,
                        cancelable: true,
                        view: window
                    });
                    copyBtn.dispatchEvent(clickEvent);
                } catch(e) { console.log('DispatchEvent fallito'); }
                
                return true;
            }
            console.log('[GeminiAuto] Pulsante Copia non trovato.');
            return false;
        })();
    '''
