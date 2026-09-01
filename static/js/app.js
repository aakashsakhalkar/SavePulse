// ==============================================================================
// 1. BACKEND API CONFIGURATION
// - On your computer (localhost), it uses the local server: ""
// - On Netlify (production), it uses your Render cloud server
// ==============================================================================
let API_BASE_URL = "https://savepulse-api.onrender.com";

if (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") {
    API_BASE_URL = "";
}

document.addEventListener('DOMContentLoaded', () => {
    const downloadForm = document.getElementById('download-form');
    const urlInput = document.getElementById('url-input');
    const pasteBtn = document.getElementById('paste-btn');
    const clearBtn = document.getElementById('clear-btn');
    const submitBtn = document.getElementById('submit-btn');
    const btnText = submitBtn.querySelector('.btn-text');
    const btnLoader = submitBtn.querySelector('.btn-loader');

    const loadingContainer = document.getElementById('loading-container');
    const resultsContainer = document.getElementById('results-container');
    const closeResultBtn = document.getElementById('close-result-btn');

    const platformBadge = document.getElementById('result-platform-badge');
    const typeBadge = document.getElementById('result-type-badge');
    const resultAuthor = document.getElementById('result-author');
    const resultTitle = document.getElementById('result-title');
    const mediaPreviewBox = document.getElementById('media-preview-box');
    const downloadOptionsList = document.getElementById('download-options-list');
    const toastContainer = document.getElementById('toast-container');

    // Input changes & clear button toggle
    urlInput.addEventListener('input', () => {
        if (urlInput.value.trim().length > 0) {
            clearBtn.classList.remove('hidden');
        } else {
            clearBtn.classList.add('hidden');
        }
    });

    clearBtn.addEventListener('click', () => {
        urlInput.value = '';
        clearBtn.classList.add('hidden');
        urlInput.focus();
    });

    // Paste from clipboard
    pasteBtn.addEventListener('click', async () => {
        try {
            const text = await navigator.clipboard.readText();
            if (text) {
                urlInput.value = text.trim();
                clearBtn.classList.remove('hidden');
                showToast('Link pasted from clipboard!', 'success');
            }
        } catch (err) {
            showToast('Please allow clipboard permissions or paste manually (Ctrl+V)', 'error');
        }
    });

    closeResultBtn.addEventListener('click', () => {
        resultsContainer.classList.add('hidden');
    });

    // Handle Form Submit
    downloadForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const url = urlInput.value.trim();

        if (!url) {
            showToast('Please paste a valid social media URL.', 'error');
            return;
        }

        // Set Loading UI
        setLoading(true);
        resultsContainer.classList.add('hidden');

        try {
            const response = await fetch(`${API_BASE_URL}/api/extract`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: url })
            });

            const data = await response.json();

            if (!response.ok || !data.success) {
                throw new Error(data.detail || 'Failed to extract media. Please verify the link is public.');
            }

            renderResults(data.data);
            showToast('Media extracted successfully!', 'success');
            // Scroll smoothly to results
            resultsContainer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        } catch (error) {
            showToast(error.message, 'error');
        } finally {
            setLoading(false);
        }
    });

    function setLoading(isLoading) {
        if (isLoading) {
            btnText.classList.add('hidden');
            btnLoader.classList.remove('hidden');
            submitBtn.disabled = true;
            loadingContainer.classList.remove('hidden');
        } else {
            btnText.classList.remove('hidden');
            btnLoader.classList.add('hidden');
            submitBtn.disabled = false;
            loadingContainer.classList.add('hidden');
        }
    }

    function renderResults(mediaData) {
        const { platform, title, author, thumbnail, media_type, items } = mediaData;

        // 1. Badges & Metadata
        const platformIcons = {
            instagram: 'fa-brands fa-instagram',
            twitter: 'fa-brands fa-x-twitter',
            reddit: 'fa-brands fa-reddit-alien',
            facebook: 'fa-brands fa-facebook',
            tiktok: 'fa-brands fa-tiktok',
            youtube: 'fa-brands fa-youtube',
            pinterest: 'fa-brands fa-pinterest',
            general: 'fa-solid fa-globe'
        };

        const iconClass = platformIcons[platform] || 'fa-solid fa-link';
        platformBadge.innerHTML = `<i class="${iconClass}"></i> ${platform.toUpperCase()}`;

        const typeIcons = {
            video: '<i class="fa-solid fa-video"></i> Video',
            image: '<i class="fa-solid fa-image"></i> Photo',
            gallery: '<i class="fa-solid fa-images"></i> Gallery',
            audio: '<i class="fa-solid fa-music"></i> Audio'
        };
        typeBadge.innerHTML = typeIcons[media_type] || '<i class="fa-solid fa-file"></i> Media';

        resultAuthor.textContent = author || '@creator';
        resultTitle.textContent = title || 'Social Media Download';

        const resultBody = document.querySelector('.result-body');

        // MULTI-ITEM POST (2 to 20+ images/videos)
        if (items && items.length > 1 && (media_type === 'gallery' || isMultiItem(items))) {
            resultBody.classList.add('is-multi');
            resultBody.innerHTML = '';

            const multiWrapper = document.createElement('div');
            multiWrapper.className = 'multi-grid-wrapper';
            multiWrapper.style.width = '100%';

            multiWrapper.innerHTML = `
                <div class="multi-grid-header">
                    <div class="multi-grid-meta">
                        <span class="multi-count-badge"><i class="fa-solid fa-layer-group"></i> ${items.length} Media Items Found</span>
                        <h3 class="post-title" style="margin-bottom:0; font-size:1.1rem;">${title || 'Multi-Item Collection'}</h3>
                    </div>
                </div>
            `;

            const cardsGrid = document.createElement('div');
            cardsGrid.className = 'media-cards-grid';

            items.forEach((item, index) => {
                const card = document.createElement('div');
                card.className = 'media-grid-card';

                const cleanExt = item.ext || (item.type === 'video' ? 'mp4' : item.type === 'audio' ? 'mp3' : 'jpg');
                const safeName = `${platform}_${Date.now()}_${index + 1}.${cleanExt}`;
                const downloadHref = `${API_BASE_URL}/api/download?url=${encodeURIComponent(item.url)}&filename=${encodeURIComponent(safeName)}`;

                // Card Preview Content
                let mediaElementHtml = '';
                if (item.type === 'video') {
                    mediaElementHtml = `<video src="${item.url}" controls poster="${thumbnail || ''}" preload="metadata" playsinline></video>`;
                } else {
                    mediaElementHtml = `<img src="${item.url || thumbnail}" alt="Item ${index + 1}" loading="lazy">`;
                }

                card.innerHTML = `
                    <span class="card-index-badge">#${index + 1}</span>
                    <span class="card-type-badge">${item.type}</span>
                    <div class="card-preview-box">
                        ${mediaElementHtml}
                    </div>
                    <div class="card-footer">
                        <div class="card-info">
                            <span class="card-quality">${item.quality || `Item #${index + 1}`}</span>
                            <span class="card-size">${(item.ext || '').toUpperCase()} • ${item.filesize_str || 'HD'}</span>
                        </div>
                        <a href="${downloadHref}" download="${safeName}" class="card-download-btn">
                            <i class="fa-solid fa-download"></i> Download ${item.type === 'video' ? 'Video' : 'Photo'}
                        </a>
                    </div>
                `;

                // Download click feedback
                const dBtn = card.querySelector('.card-download-btn');
                dBtn.addEventListener('click', () => {
                    showToast(`Downloading Item #${index + 1}...`, 'success');
                });

                cardsGrid.appendChild(card);
            });

            multiWrapper.appendChild(cardsGrid);
            resultBody.appendChild(multiWrapper);
        } else {
            // SINGLE ITEM POST
            resultBody.classList.remove('is-multi');
            resultBody.innerHTML = `
                <div class="preview-column">
                    <div id="media-preview-box" class="preview-box"></div>
                </div>
                <div class="details-column">
                    <div class="author-row">
                        <div class="author-avatar"><i class="fa-solid fa-user"></i></div>
                        <div class="author-info">
                            <span id="result-author" class="author-name">${author || '@creator'}</span>
                            <span class="author-sub">Public Creator</span>
                        </div>
                    </div>
                    <h3 id="result-title" class="post-title">${title || 'Social Media Download'}</h3>

                    <div class="downloads-section">
                        <h4 class="section-heading"><i class="fa-solid fa-download"></i> Available Formats</h4>
                        <div id="download-options-list" class="options-list"></div>
                    </div>
                </div>
            `;

            const previewBox = resultBody.querySelector('#media-preview-box');
            const optionsList = resultBody.querySelector('#download-options-list');

            const firstItem = items && items.length > 0 ? items[0] : null;
            if (firstItem && firstItem.type === 'video') {
                previewBox.innerHTML = `<video src="${firstItem.url}" controls poster="${thumbnail || ''}" preload="metadata" playsinline></video>`;
            } else if (thumbnail || (firstItem && firstItem.url)) {
                previewBox.innerHTML = `<img src="${(firstItem && firstItem.url) || thumbnail}" alt="${title || 'Preview'}">`;
            }

            if (items && items.length > 0) {
                items.forEach((item, index) => {
                    const btn = document.createElement('a');
                    btn.className = 'option-btn';
                    const cleanExt = item.ext || (item.type === 'video' ? 'mp4' : item.type === 'audio' ? 'mp3' : 'jpg');
                    const safeName = `${platform}_${Date.now()}_${index + 1}.${cleanExt}`;
                    btn.href = `${API_BASE_URL}/api/download?url=${encodeURIComponent(item.url)}&filename=${encodeURIComponent(safeName)}`;
                    btn.setAttribute('download', safeName);

                    btn.innerHTML = `
                        <div class="option-meta">
                            <span class="option-label">${item.quality || 'Download Media'}</span>
                            <span class="option-ext">${(item.ext || '').toUpperCase()} • ${item.filesize_str || 'HD'}</span>
                        </div>
                        <div class="option-icon"><i class="fa-solid fa-download"></i></div>
                    `;

                    btn.addEventListener('click', () => {
                        showToast(`Starting download: ${item.quality}`, 'success');
                    });
                    optionsList.appendChild(btn);
                });
            }
        }

        resultsContainer.classList.remove('hidden');
        resultsContainer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    function isMultiItem(items) {
        if (!items || items.length <= 1) return false;
        // If items are labeled Item #1, Item #2, Image #1, Image #2, or have distinct media ids
        return items.some(i =>
            (i.quality && (i.quality.includes('Item #') || i.quality.includes('Image #'))) ||
            (i.id && (i.id.includes('gallery') || i.id.includes('media_item')))
        );
    }

    function allUniqueItems(items) {
        // Check if items are distinct media slides (e.g. Gallery images/items vs format variants of 1 video)
        const urls = new Set(items.map(i => i.url));
        return urls.size > 1 && (items.some(i => i.id.includes('gallery') || i.id.includes('media_item')));
    }

    function renderGallerySlider(items, fallbackThumbnail) {
        const sliderContainer = document.createElement('div');
        sliderContainer.className = 'gallery-slider';

        const track = document.createElement('div');
        track.className = 'gallery-track';

        // Counter badge
        const counter = document.createElement('div');
        counter.className = 'slider-counter';
        counter.textContent = `1 / ${items.length}`;

        // Prev & Next Buttons
        const prevBtn = document.createElement('button');
        prevBtn.className = 'slider-btn prev';
        prevBtn.innerHTML = '<i class="fa-solid fa-chevron-left"></i>';
        prevBtn.title = 'Previous slide';

        const nextBtn = document.createElement('button');
        nextBtn.className = 'slider-btn next';
        nextBtn.innerHTML = '<i class="fa-solid fa-chevron-right"></i>';
        nextBtn.title = 'Next slide';

        // Dots container
        const dotsContainer = document.createElement('div');
        dotsContainer.className = 'slider-dots';

        let currentIdx = 0;
        const slideElements = [];
        const dotElements = [];

        items.forEach((item, idx) => {
            const slide = document.createElement('div');
            slide.className = `gallery-slide ${idx === 0 ? 'active' : ''}`;

            if (item.type === 'video') {
                const video = document.createElement('video');
                video.src = item.url;
                video.controls = true;
                video.poster = fallbackThumbnail;
                video.preload = 'metadata';
                slide.appendChild(video);
            } else {
                const img = document.createElement('img');
                img.src = item.url;
                img.alt = `Slide ${idx + 1}`;
                slide.appendChild(img);
            }

            track.appendChild(slide);
            slideElements.push(slide);

            const dot = document.createElement('div');
            dot.className = `slider-dot ${idx === 0 ? 'active' : ''}`;
            dot.addEventListener('click', () => goTo(idx));
            dotsContainer.appendChild(dot);
            dotElements.push(dot);
        });

        function updateSlideUI() {
            slideElements.forEach((s, i) => {
                s.classList.toggle('active', i === currentIdx);
                // Pause video if moving away
                const vid = s.querySelector('video');
                if (vid && i !== currentIdx) vid.pause();
            });
            dotElements.forEach((d, i) => d.classList.toggle('active', i === currentIdx));
            counter.textContent = `${currentIdx + 1} / ${items.length}`;
        }

        function goTo(index) {
            currentIdx = (index + items.length) % items.length;
            updateSlideUI();
        }

        prevBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            goTo(currentIdx - 1);
        });

        nextBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            goTo(currentIdx + 1);
        });

        window.galleryGoToSlide = goTo;

        sliderContainer.appendChild(counter);
        sliderContainer.appendChild(prevBtn);
        sliderContainer.appendChild(track);
        sliderContainer.appendChild(nextBtn);
        if (items.length <= 15) {
            sliderContainer.appendChild(dotsContainer);
        }

        mediaPreviewBox.appendChild(sliderContainer);
    }

    function showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;

        const icon = type === 'success' ? 'fa-solid fa-circle-check' : 'fa-solid fa-circle-exclamation';
        toast.innerHTML = `<i class="${icon}"></i> <span>${message}</span>`;

        toastContainer.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateY(10px)';
            toast.style.transition = 'all 0.3s ease';
            setTimeout(() => toast.remove(), 300);
        }, 4000);
    }
});
