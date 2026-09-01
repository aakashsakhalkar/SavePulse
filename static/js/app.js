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
            const response = await fetch('/api/extract', {
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

        // 2. Render Media Preview
        mediaPreviewBox.innerHTML = '';
        const firstItem = items && items.length > 0 ? items[0] : null;

        if (media_type === 'video' && firstItem) {
            const videoEl = document.createElement('video');
            videoEl.src = firstItem.url;
            videoEl.controls = true;
            videoEl.poster = thumbnail;
            videoEl.preload = 'metadata';
            mediaPreviewBox.appendChild(videoEl);
        } else if (thumbnail) {
            const imgEl = document.createElement('img');
            imgEl.src = thumbnail;
            imgEl.alt = title;
            mediaPreviewBox.appendChild(imgEl);
        } else {
            mediaPreviewBox.innerHTML = `<div style="padding: 2rem; color: var(--text-muted);"><i class="fa-solid fa-file-arrow-down fa-3x"></i><p style="margin-top:0.5rem">Ready to Download</p></div>`;
        }

        // 3. Render Download Buttons
        downloadOptionsList.innerHTML = '';

        if (!items || items.length === 0) {
            downloadOptionsList.innerHTML = `<p style="color:var(--text-muted);">No direct download formats detected.</p>`;
        } else {
            items.forEach((item, index) => {
                const btn = document.createElement('a');
                btn.className = 'option-btn';
                
                // Safe filename construction
                const cleanExt = item.ext || (item.type === 'video' ? 'mp4' : item.type === 'audio' ? 'mp3' : 'jpg');
                const safeName = `${platform}_${Date.now()}_${index + 1}.${cleanExt}`;
                
                // Route through our backend download proxy to guarantee attachment download without CORS issues
                btn.href = `/api/download?url=${encodeURIComponent(item.url)}&filename=${encodeURIComponent(safeName)}`;
                btn.setAttribute('download', safeName);
                
                const itemIcon = item.type === 'video' ? 'fa-solid fa-video' : item.type === 'audio' ? 'fa-solid fa-music' : 'fa-solid fa-image';

                btn.innerHTML = `
                    <div class="option-meta">
                        <span class="option-label">${item.quality || 'Download Media'}</span>
                        <span class="option-ext">${(item.ext || '').toUpperCase()} • ${item.filesize_str || 'HD'}</span>
                    </div>
                    <div class="option-icon">
                        <i class="fa-solid fa-download"></i>
                    </div>
                `;

                // Add visual click feedback
                btn.addEventListener('click', () => {
                    showToast(`Starting download: ${item.quality}`, 'success');
                });

                downloadOptionsList.appendChild(btn);
            });
        }

        resultsContainer.classList.remove('hidden');
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
