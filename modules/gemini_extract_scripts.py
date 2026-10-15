from modules.gemini_response_scripts import _copy_button_helpers


def get_js_extract(expected_count: int, keyed_mode: bool = False) -> str:
    return f"""
        (function() {{
            const expectedCount = {expected_count};
            const keyedMode = {str(keyed_mode).lower()};
            {_copy_button_helpers()}

            function isGenerationFinished() {{
                const copyState = buildState(false);
                const copyPresent = (
                    copyState.ready
                    || (
                        copyState.status !== 'missing'
                        && copyState.visible
                        && copyState.enabled
                        && copyState.rendered
                        && (
                            copyState.associated_with_response
                            || copyState.in_response_container
                            || copyState.response_container_found
                        )
                    )
                );
                const feedbackIcons = document.querySelector('button[aria-label*="Buona risposta"]') ||
                    document.querySelector('button[aria-label*="Good response"]') ||
                    document.querySelector('[data-testid="thumbs-up-button"]') ||
                    document.querySelector('mat-icon[svgicon*="thumb_up"]');
                const stopBtn = document.querySelector('button[aria-label*="Interrompi"]') ||
                    document.querySelector('button[aria-label*="Stop"]');
                const sendBtn = document.querySelector('button[aria-label*="Invia"]') ||
                    document.querySelector('button[aria-label*="Send"]');
                return copyPresent || feedbackIcons !== null || (sendBtn && !sendBtn.disabled && !stopBtn);
            }}

            if (!isGenerationFinished()) return "NOT_FINISHED";

            function isCompleteResult(parsed) {{
                if (!parsed || typeof parsed !== 'object') return false;
                const keys = Object.keys(parsed).filter(k => /^block_\\d+$/.test(k));
                if (keyedMode) return keys.includes('block_1');
                if (!keys.length || expectedCount <= 0) return keys.length > 0;
                for (let i = 1; i <= expectedCount; i++) {{
                    const value = parsed[`block_${{i}}`];
                    if (typeof value === 'string') {{
                        if (!value.trim()) return false;
                        continue;
                    }}
                    if (!value || typeof value !== 'object') return false;
                    if (!('it' in value) && !('text' in value)) return false;
                }}
                return true;
            }}

            function extractJson(text) {{
                if (!text) return null;
                const startIdx = text.indexOf('{{');
                const endIdx = text.lastIndexOf('}}');
                if (startIdx !== -1 && endIdx !== -1 && endIdx > startIdx) {{
                    const possibleJson = text.substring(startIdx, endIdx + 1);
                    if (possibleJson.includes('"block_1"')) return possibleJson;
                }}
                return null;
            }}

            function resolveCandidate(text) {{
                if (!text) return null;
                const jsonCandidate = extractJson(text);
                if (jsonCandidate) {{
                    try {{
                        JSON.parse(jsonCandidate);
                        return jsonCandidate;
                    }} catch (error) {{
                        const recovered = extractStructuredBlocks(text) || parsePlainBlocks(text);
                        if (recovered) return recovered;
                        return jsonCandidate;
                    }}
                }}
                return extractStructuredBlocks(text) || parsePlainBlocks(text);
            }}

            function extractStructuredBlocks(text) {{
                if (!text || !text.includes('block_1')) return null;
                const blocks = {{}};
                const regex = /"?block_(\\d+)"?\\s*[:=]\\s*"([\\s\\S]*?)(?="\\s*,\\s*"block_\\d+"\\s*:|"$|\\n\\s*"?block_\\d+"?\\s*[:=]|\\n\\s*}}|\\s*}}\\s*$)/g;
                let match;
                while ((match = regex.exec(text)) !== null) blocks[`block_${{match[1]}}`] = match[2].replace(/\\\\n/g, '\\n').replace(/\\\\r/g, '\\r').replace(/\\\\t/g, '\\t').replace(/\\"/g, '"').replace(/\\\\\\\\/g, '\\\\').trim();
                return Object.keys(blocks).length ? JSON.stringify(blocks) : null;
            }}

            function parsePlainBlocks(text) {{
                if (!text || !text.includes('block_1')) return null;
                const blocks = {{}};
                const regex = /"?block_(\\d+)"?\\s*[:=]\\s*["']?(.+?)["']?(?:,?$)/gm;
                let match;
                while ((match = regex.exec(text)) !== null) blocks[`block_${{match[1]}}`] = match[2].trim();
                return Object.keys(blocks).length ? JSON.stringify(blocks) : null;
            }}

            let resultData = null;
            for (const block of document.querySelectorAll('pre, code, .code-block-body')) {{
                resultData = resolveCandidate(block.innerText);
                if (resultData) break;
            }}

            if (!resultData) {{
                for (const selector of ['.message-content', '[data-testid="response-container"]', '.markdown']) {{
                    const elements = document.querySelectorAll(selector);
                    if (elements.length > 0) {{
                        const lastText = elements[elements.length - 1].innerText;
                        resultData = resolveCandidate(lastText);
                        if (resultData) break;
                    }}
                }}
            }}

            if (!resultData) return "JSON_NOT_FOUND";
            try {{
                return isCompleteResult(JSON.parse(resultData)) ? resultData : "INCOMPLETE_JSON";
            }} catch (error) {{
                return "INVALID_JSON";
            }}
        }})();
    """
