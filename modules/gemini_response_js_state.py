from modules.gemini_response_js_base import get_copy_button_base_js

def get_copy_button_helpers_js() -> str:
    return f"""
            {get_copy_button_base_js()}

            function classifyButton(button, responseContainer) {{
                const labels = collectLabels(button);
                const exactResponse = labels.some(matchesResponseLabel);
                const exactPrompt = labels.some(matchesPromptLabel);
                const copyIcon = hasCopyIcon(button);
                const visible = isVisible(button);
                const enabled = isEnabled(button);
                const rendered = isRendered(button);
                const inResponseContainer = !!(responseContainer && responseContainer.contains(button));
                const associatedWithResponse = isAssociatedWithResponse(button, responseContainer);
                const genericResponseCopy = (
                    copyIcon
                    && !exactPrompt
                    && (associatedWithResponse || inResponseContainer)
                    && responseHasUsefulContent(responseContainer)
                );
                if ((exactResponse || genericResponseCopy) && visible && !rendered) {{
                    try {{ button.scrollIntoView({{ block: 'center', inline: 'center' }}); }} catch (error) {{}}
                }}
                return {{
                    button,
                    labels,
                    exactResponse,
                    exactPrompt,
                    copyIcon,
                    genericResponseCopy,
                    visible,
                    enabled,
                    rendered,
                    inResponseContainer,
                    associatedWithResponse
                }};
            }}

            function findPromptButtons() {{
                return Array.from(document.querySelectorAll('button'))
                    .map(button => classifyButton(button, null))
                    .filter(info => info.exactPrompt && info.visible);
            }}

            function findImageMenuItem() {{
                const responseContainer = findLatestResponseContainer();
                const items = Array.from(document.querySelectorAll('[role="menuitem"], [role="menuitemradio"], [role="option"], button, div, li, span'));
                return items
                    .filter(isVisible)
                    .map(button => classifyButton(button, responseContainer))
                    .find(info => info.labels.some(label => label.includes('copia immagine') || label.includes('copy image'))) || null;
            }}

            function findMoreButton() {{
                const responseContainer = findLatestResponseContainer();
                const items = Array.from(document.querySelectorAll('button, div[role="button"], [aria-label], [mattooltip], [title]'));
                return items
                    .filter(isVisible)
                    .map(button => classifyButton(button, responseContainer))
                    .find(info => (
                        (info.inResponseContainer || info.associatedWithResponse)
                        && info.labels.some(label =>
                            label === 'altro'
                            || label === 'more'
                            || label.includes('altro')
                            || label.includes('more')
                            || label.includes('più opzioni')
                            || label.includes('more options')
                        )
                    )) || null;
            }}

            function findResponseCopyButton() {{
                const responseContainer = findLatestResponseContainer();
                const orderedRoots = [responseContainer, document].filter(Boolean);
                const seen = new Set();
                const candidates = [];

                for (const root of orderedRoots) {{
                    for (const selector of RESPONSE_SELECTORS) {{
                        for (const button of root.querySelectorAll(selector)) {{
                            if (seen.has(button)) continue;
                            seen.add(button);
                            candidates.push(classifyButton(button, responseContainer));
                        }}
                    }}
                }}

                for (const button of document.querySelectorAll('button')) {{
                    if (seen.has(button)) continue;
                    const info = classifyButton(button, responseContainer);
                    if (info.exactResponse || info.genericResponseCopy || info.exactPrompt) candidates.push(info);
                }}

                candidates.sort((left, right) => {{
                    const leftScore = (
                        Number(left.inResponseContainer) * 10
                        + Number(left.associatedWithResponse) * 6
                        + Number(left.exactResponse) * 6
                        + Number(left.genericResponseCopy) * 4
                        + Number(left.rendered) * 2
                        + Number(left.enabled)
                    );
                    const rightScore = (
                        Number(right.inResponseContainer) * 10
                        + Number(right.associatedWithResponse) * 6
                        + Number(right.exactResponse) * 6
                        + Number(right.genericResponseCopy) * 4
                        + Number(right.rendered) * 2
                        + Number(right.enabled)
                    );
                    return rightScore - leftScore;
                }});

                const candidate = candidates.find(info => (
                    !info.exactPrompt && (info.exactResponse || info.genericResponseCopy)
                )) || null;
                return {{ responseContainer, candidate }};
            }}

            function buildState(includeButton = false) {{
                const result = findResponseCopyButton();
                const candidate = result.candidate;
                const imageMenuItem = findImageMenuItem();
                const moreButton = findMoreButton();
                const promptButtons = findPromptButtons();
                const state = {{
                    status: 'missing',
                    ready: false,
                    labels: [],
                    exact_response_match: false,
                    exact_prompt_match: false,
                    generic_copy_match: false,
                    visible: false,
                    enabled: false,
                    rendered: false,
                    in_response_container: false,
                    associated_with_response: false,
                    prompt_button_visible: promptButtons.length > 0,
                    prompt_button_count: promptButtons.length,
                    response_container_found: !!result.responseContainer,
                    response_has_useful_content: responseHasUsefulContent(result.responseContainer),
                    image_menu_item_found: !!imageMenuItem,
                    more_button_found: !!moreButton
                }};

                if (!candidate && !imageMenuItem && !moreButton) return state;
                if (candidate) {{
                    state.status = 'found';
                    state.labels = candidate.labels;
                    state.exact_response_match = candidate.exactResponse;
                    state.exact_prompt_match = candidate.exactPrompt;
                    state.generic_copy_match = candidate.genericResponseCopy;
                    state.visible = candidate.visible;
                    state.enabled = candidate.enabled;
                    state.rendered = candidate.rendered;
                    state.in_response_container = candidate.inResponseContainer;
                    state.associated_with_response = candidate.associatedWithResponse;
                    state.ready = (
                        !candidate.exactPrompt
                        && (candidate.exactResponse || candidate.genericResponseCopy)
                        && candidate.visible
                        && candidate.enabled
                        && candidate.rendered
                        && (candidate.associatedWithResponse || candidate.inResponseContainer)
                        && (state.response_has_useful_content || candidate.inResponseContainer)
                    );
                    if (includeButton) state.button = candidate.button;
                    return state;
                }}
                if (imageMenuItem) {{
                    state.status = 'found';
                    state.labels = imageMenuItem.labels;
                    state.visible = imageMenuItem.visible;
                    state.enabled = imageMenuItem.enabled;
                    state.rendered = imageMenuItem.rendered;
                    if (includeButton) state.button = imageMenuItem.button;
                    state.ready = imageMenuItem.visible && imageMenuItem.enabled && imageMenuItem.rendered;
                    return state;
                }}
                state.status = 'needs_menu_open';
                state.labels = moreButton.labels;
                state.visible = moreButton.visible;
                state.enabled = moreButton.enabled;
                state.rendered = moreButton.rendered;
                state.in_response_container = moreButton.inResponseContainer;
                state.associated_with_response = moreButton.associatedWithResponse;
                state.ready = (
                    moreButton.visible
                    && moreButton.enabled
                    && moreButton.rendered
                    && state.response_container_found
                    && (moreButton.associatedWithResponse || moreButton.inResponseContainer)
                );
                if (includeButton) state.button = moreButton.button;
                return state;
            }}
    """
