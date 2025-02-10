/* library functions */

async function hash(str) {
    // https://lusbuab.medium.com/calculating-sha-1-in-the-browser-f4237a6d7bd0
    const enc = new TextEncoder();
    const hash = await crypto.subtle.digest("SHA-1", enc.encode(str));
    return Array.from(new Uint8Array(hash))
        .map(v => v.toString(16).padStart(2, "0"))
        .join("");
}

function getElementById(id) {
    return document.getElementById(id);
}

function getChildren(element, tag, cls) {
    if (tag !== undefined) {
        tag = tag.toUpperCase();
    }
    let elements = [];
    for (const item of element.children) {
        let tagMatch = (tag === undefined);
        let clsMatch = (cls === undefined);
        if (tag !== undefined && tag === item.tagName) {
            tagMatch = true;
        }
        if (cls !== undefined && item.classList.contains(cls)) {
            clsMatch = true;
        }
        if (tagMatch && clsMatch) {
            elements.push(item);
        }
    }
    return elements;
}

function createText(str) {
    return document.createTextNode(str);
}

function appendSpace(element) {
    element.appendChild(createSpace());
}

function createSpace() {
    return createText(" ");
}

function createElement(tag, id, cls, str) {
    let element = document.createElement(tag);
    if (id !== undefined) {
        element.setAttribute("id", id);
    }
    if (cls !== undefined) {
        element.setAttribute("class", cls);
    }
    if (str !== undefined) {
        element.appendChild(createText(str));
    }
    return element;
}

function toggleClassReturnPresent(element, cls) {
    element.classList.toggle(cls);
    return element.classList.contains(cls);
}

/* helper functions */

function createErrorElement(message) {
    let element = createElement("div", undefined, "error");
    element.appendChild(createText(`Error: ${message}`));
    return element;
}

function createButtonElement(text) {
    let button = createElement("button");
    button.setAttribute("type", "button");
    button.appendChild(createText(text));
    return button;
}

function createContentClassToggleButtonWithCallback(contentTag, toggleClass, presentFn, presentText = "hide", absentText = "show") {
    let button = createButtonElement(absentText);
    let content = createElement(contentTag, undefined, toggleClass);
    button.addEventListener("click", async function () {
        const present = toggleClassReturnPresent(content, toggleClass);
        button.innerHTML = present ? absentText : presentText;
        if (!present) {
            await presentFn();
        }
    });
    return [button, content];
}

/* main code */


function createImageRevisionDetailTitle(title) {
    return createElement("span", undefined, "revision-detail-title", title);
}

function createRecursiveListFromObjectOrValue(obj) {
    function createListKeyValue(key, value) {
        let item = createElement("li");
        item.appendChild(createText(`${key} `));
        item.appendChild(createElement("span", undefined, "revision-detail-value", value));
        return item
    }

    let list = createElement("ul");
    if (Array.isArray(obj)) {
        for (const index in obj) {
            const value = obj[index];
            if (typeof value === 'object') {
                let subItem = list.appendChild(createElement("li", undefined, undefined, index));
                subItem.appendChild(createRecursiveListFromObjectOrValue(value));
            } else {
                list.appendChild(createElement("li", undefined, "revision-detail-value", value));
            }
        }
    } else if (typeof obj === 'object') {
        for (const [key, value] of Object.entries(obj)) {
            if (value === null || value === undefined) {
                continue;
            }
            if (Array.isArray(value) || typeof value === 'object') {
                let item = list.appendChild(createElement("li", undefined, undefined, key));
                item.appendChild(createRecursiveListFromObjectOrValue(value));
            } else {
                list.appendChild(createListKeyValue(key, value));
            }
        }
    }
    return list;
}

function createImageRevisionDetailMetadata(metadata) {
    let item = createElement("li");
    item.appendChild(createImageRevisionDetailTitle("metadata"));
    item.appendChild(createRecursiveListFromObjectOrValue(metadata));
    return item;
}

function createImageRevisionDetailConfiguration(configuration) {
    let item = createElement("li");
    item.appendChild(createImageRevisionDetailTitle("configuration"));
    item.appendChild(createRecursiveListFromObjectOrValue(configuration));
    return item;
}

function createImageRevisionDetailLayers(layers) {
    let item = createElement("li");
    item.appendChild(createImageRevisionDetailTitle("layers"));
    item.appendChild(createRecursiveListFromObjectOrValue(layers));
    return item;
}

async function buildImageRevision(element, repository, revision, manifest) {
    if (!manifest.metadata || !manifest.configuration || !manifest.layers) {
        element.replaceChildren(createText("Incomplete manifest data."));
        return;
    }
    let list = createElement("ul");
    element.replaceChildren(list);
    list.appendChild(await createImageRevisionDetailMetadata(manifest.metadata));
    list.appendChild(await createImageRevisionDetailConfiguration(manifest.configuration));
    list.appendChild(await createImageRevisionDetailLayers(manifest.layers));
}

async function moveRepositoryRevisionIdTo(repository, revisionId, target) {
    const revisionDigestId = await makeRepositoryRevisionId(repository, revisionId);
    const item = getElementById(revisionDigestId);
    if (item === null) {
        throw Error(`Revision ${revisionId} not found in repository: ${repository.name}`);
    }
    return target.appendChild(item);
}

async function buildIndexRevision(element, repository, revision, manifests) {
    if (!manifests) {
        element.replaceChildren(createText("No manifests found in index."));
        return;
    }
    let target = element.appendChild(createElement("ul"));
    for (const manifest of manifests) {
        let item = await moveRepositoryRevisionIdTo(repository, manifest.digest, target);
        const platforms = getChildren(item, "span", "platform");
        if (platforms.length !== 1) {
            throw Error(`Could not add platform information to ${manifest.digest}`);
        }
        platforms[0].innerHTML = manifest.platform;
    }
}

async function buildRevision(element, repository, revision, manifest) {
    const type = manifest.type;
    if (!type) {
        element.replaceChildren(createText("No type found in manifest."));
        return;
    }
    if (type === "image") {
        await buildImageRevision(element, repository, revision, manifest);
    } else if (type === "index") {
        if (!manifest.manifests || manifest.manifests.length === 0) {
            element.replaceChildren(createText("No manifests found in index."));
            return;
        }
        await buildIndexRevision(element, repository, revision, manifest.manifests);
    } else {
        element.replaceChildren(createText("Unknown manifest type."));
    }
}

async function getRevision(repository, revision) {
    const response = await fetch(`/revisions/${revision}/repository/${repository.name}`)
    checkResponse(response, "Unable to get revision info");
    return await response.json();
}

async function loadRevision(element, repository, revision) {
    const manifest = await getRevision(repository, revision);
    if (!manifest) {
        element.replaceChildren(createText("No revisions found."));
        return;
    }
    await buildRevision(element, repository, revision, manifest);
}

async function tryLoadRevision(element, repository, revision) {
    try {
        await loadRevision(element, repository, revision);
    } catch (error) {
        element.replaceChildren(createErrorElement(error.message));
        console.error("Error at loadRevision :", error.message);
        throw error;
    }
}

async function makeRepositoryRevisionId(repository, revision) {
    return await hash(`${repository.name}|${revision}`);
}

function createRevisionId(revisionId) {
    let span = createElement("span");
    span.setAttribute("class", "revision-id");
    span.appendChild(createText(revisionId));
    return span;
}

function createRevisionPlatform() {
    let span = createElement("span");
    span.setAttribute("class", "platform");
    return span;
}

function createRevisionTag(tag) {
    let span = createElement("span");
    span.setAttribute("class", "tag-id");
    span.appendChild(createText(tag));
    return span;
}

function createRevisionTags(tags) {
    let span = createElement("span");
    tags.sort();
    for (const tag of tags) {
        appendSpace(span);
        span.appendChild(createRevisionTag(tag));
    }
    return span;
}

async function createRevision(parent, repository, revisionId, revisionData) {
    let revisionDigestId = await makeRepositoryRevisionId(repository, revisionId);
    const [button, content] = createContentClassToggleButtonWithCallback("div", "hidden", async () => {
        await tryLoadRevision(content, repository, revisionId);
    });
    let item = parent.appendChild(createElement("li", revisionDigestId));
    item.appendChild(createRevisionId(revisionId));
    appendSpace(item);
    item.appendChild(button);
    appendSpace(item);
    item.appendChild(createRevisionPlatform());
    if (revisionData && revisionData.tags && revisionData.tags.length > 0) {
        item.appendChild(createRevisionTags(revisionData.tags));
    }
    item.appendChild(content);
}

async function buildRepositoryRevisions(element, repository, revisions) {
    let target = createElement("ul");
    element.replaceChildren(target);
    for (const [revisionId, revisionData] of Object.entries(revisions)) {
        await createRevision(target, repository, revisionId, revisionData);
    }
}

function checkResponse(response, message, debugResponse = false) {
    if (!response.ok) {
        if (debugResponse === true) {
            console.debug(response);
        }
        throw Error(`${message} (${response.status} ${response.statusText})`);
    }
}

async function getRepositoryRevisions(repository) {
    const response = await fetch(`/repositories/${repository.name}`);
    checkResponse(response, "Unable to get repository info");
    return await response.json();
}

async function loadRepository(element, repository) {
    const data = await getRepositoryRevisions(repository);
    if (!data || !data.revisions || Object.keys(data.revisions).length === 0) {
        element.replaceChildren(createText("No revisions found."));
        return;
    }
    await buildRepositoryRevisions(element, repository, data.revisions);
}

async function tryLoadRepository(element, repository) {
    try {
        await loadRepository(element, repository);
    } catch (error) {
        element.replaceChildren(createErrorElement(error.message));
        console.error("Error at loadRepository :", error.message);
        throw error;
    }
}

function createRepositoryTitle(repository) {
    let title = createElement("span", undefined, "repository-title");
    title.appendChild(createElement("span", undefined, "repository-name-short", repository.short_name));
    if (repository.name !== repository.short_name) {
        title.appendChild(createText(` (${repository.name})`));
    }
    return title;
}

async function createRepository(parent, repository) {
    const [button, content] = createContentClassToggleButtonWithCallback("div", "hidden", async () => {
        await tryLoadRepository(content, repository);
    });
    let item = parent.appendChild(createElement("li", repository.digest_name, "repository"));
    item.appendChild(button);
    appendSpace(item);
    item.appendChild(createRepositoryTitle(repository));
    item.appendChild(content);
}

function repositoryShortName(name) {
    const index = name.lastIndexOf("/");
    if (index === -1) {
        return name;
    }
    return name.substring(index + 1);
}

function buildRepositoryObject(repository) {
    return {
        name: repository,
        short_name: repositoryShortName(repository),
        digest_name: hash(repository.name)  // async
    };
}

function compareRepositoryShortNames(a, b) {
    a = a.short_name.toLowerCase();
    b = b.short_name.toLowerCase();
    return a.localeCompare(b);
}

async function buildRepositoryNames(repositories) {
    repositories = repositories.map(buildRepositoryObject).sort(compareRepositoryShortNames);
    for (const repository of repositories) {
        repository.digest_name = await repository.digest_name;
    }
    return repositories;
}

async function buildRegistry(element, repositories) {
    let target = createElement("ul", "repositories");
    element.replaceChildren(target);
    repositories = await buildRepositoryNames(repositories);
    for (const repository of repositories) {
        await createRepository(target, repository);
    }
}

async function getRegistry() {
    const response = await fetch("/repositories");
    if (!response.ok) {
        throw Error("Unable to load repositories");
    }
    return await response.json();
}

async function LoadRegistry(element) {
    const data = await getRegistry();
    if (!data || !data.repositories || data.repositories.length === 0) {
        element.replaceChildren(createText("No repositories found."));
        return;
    }
    await buildRegistry(element, data.repositories);
}

async function TryLoadRegistry(targetId) {
    let element = getElementById(targetId);
    try {
        await LoadRegistry(element);
    } catch (error) {
        element.replaceChildren(createErrorElement(error.message));
        console.error("Error at LoadRegistry :", error.message);
        throw error;
    }
}

function filterTargetChildrenByText(search, target_id) {
    let target = getElementById(target_id);
    for (let children of target.children) {
        children.hidden = !children.textContent.includes(search);
    }
}

function setupSearch(inputId, targetId) {
    let input = getElementById(inputId);
    input.addEventListener("input", event => {
        filterTargetChildrenByText(event.target.value, targetId);
    });
}

document.addEventListener("DOMContentLoaded", async function () {
    setupSearch("search", "repositories");
    await TryLoadRegistry("registry");
});
