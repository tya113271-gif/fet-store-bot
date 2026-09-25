// [[ State & DOM References ]] //
let currentConfig = {};
let botData = {};

// Safe Element Helper
function safeElem(id) {
    return document.getElementById(id);
}

// Navigation Tabs
document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
        btn.classList.add('active');
        const tabId = btn.dataset.tab;
        const targetPane = document.getElementById(tabId);
        if (targetPane) targetPane.classList.add('active');
    });
});

// [[ Live Preview Sync - Ticket Panel ]] //
const ticketTitleInput = safeElem('ticket-title-input');
const ticketDescInput = safeElem('ticket-desc-input');
const ticketPlaceholderInput = safeElem('ticket-placeholder-input');
const ticketColorInput = safeElem('ticket-color-input');

const previewTitle = safeElem('preview-title');
const previewDesc = safeElem('preview-desc');
const previewSelectPlaceholder = safeElem('preview-select-placeholder');
const previewEmbed = safeElem('preview-embed');

if (ticketTitleInput && previewTitle) {
    ticketTitleInput.addEventListener('input', (e) => {
        previewTitle.innerText = e.target.value || 'FET STORE - Support & Ticket System';
    });
}

if (ticketDescInput && previewDesc) {
    ticketDescInput.addEventListener('input', (e) => {
        previewDesc.innerHTML = (e.target.value || '').replace(/\n/g, '<br>');
    });
}

if (ticketPlaceholderInput && previewSelectPlaceholder) {
    ticketPlaceholderInput.addEventListener('input', (e) => {
        previewSelectPlaceholder.innerText = e.target.value || '📂 - اختر نوع الخدمة المطلوبة';
    });
}

if (ticketColorInput && previewEmbed) {
    ticketColorInput.addEventListener('input', (e) => {
        previewEmbed.style.borderLeftColor = e.target.value;
    });
}

// [[ Live Preview Sync - Updates Broadcaster ]] //
const updateProductInput = safeElem('update-product-input');
const updateDescInput = safeElem('update-desc-input');
const previewUpdateTitle = safeElem('preview-update-title');
const previewUpdateDesc = safeElem('preview-update-desc');

if (updateProductInput && previewUpdateTitle) {
    updateProductInput.addEventListener('input', (e) => {
        const val = e.target.value.trim();
        previewUpdateTitle.innerText = val ? `🚀 تم تحديث المنتج: ${val}` : '🚀 تم تحديث المنتج: FET INVENTORY V1.0';
    });
}

if (updateDescInput && previewUpdateDesc) {
    updateDescInput.addEventListener('input', (e) => {
        previewUpdateDesc.innerHTML = (e.target.value || '').replace(/\n/g, '<br>');
    });
}

// [[ Live Preview Sync - Rules Broadcaster ]] //
const rulesTitleInput = safeElem('rules-title-input');
const rulesSubtitleInput = safeElem('rules-subtitle-input');
const rulesTextInput = safeElem('rules-text-input');
const rulesColorInput = safeElem('rules-color-input');
const rulesBannerCheckbox = safeElem('rules-banner-checkbox');

const previewRulesTitle = safeElem('preview-rules-title');
const previewRulesDesc = safeElem('preview-rules-desc');
const previewRulesEmbed = safeElem('preview-rules-embed');
const previewRulesBannerContainer = safeElem('preview-rules-banner-container');

function updateRulesPreview() {
    if (previewRulesTitle && rulesTitleInput) {
        previewRulesTitle.innerText = rulesTitleInput.value || '📜 قوانين وشروط متجر FET STORE الرسمية';
    }
    if (previewRulesDesc && rulesTextInput) {
        const sub = rulesSubtitleInput ? rulesSubtitleInput.value.trim() : '';
        const rules = (rulesTextInput.value || '').replace(/\n/g, '<br>');
        previewRulesDesc.innerHTML = sub ? `${sub}<br><br>${rules}` : rules;
    }
    if (previewRulesEmbed && rulesColorInput) {
        previewRulesEmbed.style.borderLeftColor = rulesColorInput.value;
    }
    if (previewRulesBannerContainer && rulesBannerCheckbox) {
        previewRulesBannerContainer.style.display = rulesBannerCheckbox.checked ? 'block' : 'none';
    }
}

if (rulesTitleInput) rulesTitleInput.addEventListener('input', updateRulesPreview);
if (rulesSubtitleInput) rulesSubtitleInput.addEventListener('input', updateRulesPreview);
if (rulesTextInput) rulesTextInput.addEventListener('input', updateRulesPreview);
if (rulesColorInput) rulesColorInput.addEventListener('input', updateRulesPreview);
if (rulesBannerCheckbox) rulesBannerCheckbox.addEventListener('change', updateRulesPreview);

// [[ API - Fetch Bot Status & Channels ]] //
async function loadStatus() {
    try {
        const res = await fetch('/api/status');
        const data = await res.json();
        botData = data;
        currentConfig = data.config || {};

        const botStatusDot = document.querySelector('.status-dot');
        const botStatusText = safeElem('bot-status-text');
        const botProfileCard = safeElem('bot-profile-card');
        const botUsername = safeElem('bot-username');
        const botAvatar = safeElem('bot-avatar');

        if (data.online) {
            if (botStatusDot) botStatusDot.className = 'status-dot online';
            if (botStatusText) botStatusText.innerText = 'البوت متصل بنجاح 🟢';
            if (botProfileCard) botProfileCard.classList.remove('hidden');
            if (botUsername && data.bot_user) botUsername.innerText = data.bot_user;
            if (botAvatar && data.bot_avatar) botAvatar.src = data.bot_avatar;
        } else {
            if (botStatusDot) botStatusDot.className = 'status-dot offline';
            if (botStatusText) botStatusText.innerText = data.bot_error ? `خطأ: ${data.bot_error}` : 'البوت غير متصل 🔴 (يرجى إدخال التوكن)';
            if (botProfileCard) botProfileCard.classList.add('hidden');
        }

        // Fill channels & roles dropdowns
        if (data.guilds && Array.isArray(data.guilds)) {
            populateDropdowns(data.guilds);
        }
        
        // Fill initial inputs with config
        const tokenInp = safeElem('token-input');
        const staffInp = safeElem('staff-role-id-manual');
        const catInp = safeElem('category-id-manual');
        const closedCatInp = safeElem('closed-category-id-manual');

        if (tokenInp && currentConfig.token) tokenInp.value = currentConfig.token;
        if (staffInp && currentConfig.staff_role_id) staffInp.value = currentConfig.staff_role_id;
        if (catInp && currentConfig.ticket_category_id) catInp.value = currentConfig.ticket_category_id;
        if (closedCatInp && currentConfig.closed_category_id) closedCatInp.value = currentConfig.closed_category_id;

    } catch (e) {
        console.error('Error fetching status:', e);
    }
}

function populateDropdowns(guilds) {
    const ticketChannelSelect = safeElem('ticket-channel-select');
    const updateChannelSelect = safeElem('update-channel-select');
    const rulesChannelSelect = safeElem('rules-channel-select');
    const staffRoleSelect = safeElem('staff-role-select');
    const categorySelect = safeElem('ticket-category-select');
    const closedCategorySelect = safeElem('closed-category-select');

    if (ticketChannelSelect) ticketChannelSelect.innerHTML = '<option value="">-- اختر الروم من سيرفرك --</option>';
    if (updateChannelSelect) updateChannelSelect.innerHTML = '<option value="">-- اختر الروم --</option>';
    if (rulesChannelSelect) rulesChannelSelect.innerHTML = '<option value="">-- اختر الروم --</option>';
    if (staffRoleSelect) staffRoleSelect.innerHTML = '<option value="">-- اختر الرتبة التي تستقبل التكتات --</option>';
    if (categorySelect) categorySelect.innerHTML = '<option value="">-- اختر قسم التكتات الفعالة --</option>';
    if (closedCategorySelect) closedCategorySelect.innerHTML = '<option value="">-- اختر قسم التكتات المغلقة --</option>';

    guilds.forEach(g => {
        // Text Channels
        if (g.channels) {
            g.channels.forEach(ch => {
                if (ticketChannelSelect) ticketChannelSelect.add(new Option(`# ${ch.name} (${g.name})`, ch.id));
                if (updateChannelSelect) updateChannelSelect.add(new Option(`# ${ch.name} (${g.name})`, ch.id));
                if (rulesChannelSelect) rulesChannelSelect.add(new Option(`# ${ch.name} (${g.name})`, ch.id));
            });
        }
        // Roles
        if (g.roles) {
            g.roles.forEach(r => {
                if (staffRoleSelect) staffRoleSelect.add(new Option(`@${r.name}`, r.id));
            });
        }
        // Categories
        if (g.categories) {
            g.categories.forEach(cat => {
                if (categorySelect) categorySelect.add(new Option(`📁 ${cat.name}`, cat.id));
                if (closedCategorySelect) closedCategorySelect.add(new Option(`📁 ${cat.name}`, cat.id));
            });
        }
    });

    if (ticketChannelSelect && currentConfig.ticket_channel_id) ticketChannelSelect.value = currentConfig.ticket_channel_id;
    if (updateChannelSelect && currentConfig.updates_channel_id) updateChannelSelect.value = currentConfig.updates_channel_id;
    if (staffRoleSelect && currentConfig.staff_role_id) staffRoleSelect.value = currentConfig.staff_role_id;
    if (categorySelect && currentConfig.ticket_category_id) categorySelect.value = currentConfig.ticket_category_id;
    if (closedCategorySelect && currentConfig.closed_category_id) closedCategorySelect.value = currentConfig.closed_category_id;
}

// [[ Send Ticket Panel to Discord ]] //
const btnSendTicket = safeElem('btn-send-ticket');
if (btnSendTicket) {
    btnSendTicket.addEventListener('click', async () => {
        const ticketChannelSelect = safeElem('ticket-channel-select');
        const channelId = ticketChannelSelect ? ticketChannelSelect.value : '';
        if (!channelId) {
            return showToast('⚠️ يرجى اختيار الروم أولاً!');
        }

        const payload = {
            channel_id: channelId,
            title: ticketTitleInput ? ticketTitleInput.value : 'FET STORE - Support & Ticket System',
            description: ticketDescInput ? ticketDescInput.value : '',
            placeholder: ticketPlaceholderInput ? ticketPlaceholderInput.value : '📂 - اختر نوع الخدمة المطلوبة',
            color: ticketColorInput ? ticketColorInput.value : '#00ff41'
        };

        try {
            showToast('⏳ جاري إرسال التكت إلى الديسكورد...');
            const res = await fetch('/api/ticket/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const result = await res.json();
            if (result.status === 'ok') {
                showToast('✅ تم إرسال رسالة التكت بنجاح إلى الديسكورد!');
            } else {
                showToast('❌ خطأ: ' + result.message);
            }
        } catch (e) {
            showToast('❌ تعذر الإرسال: ' + e.message);
        }
    });
}

// [[ Publish Product Update to Discord ]] //
const btnSendUpdate = safeElem('btn-send-update');
if (btnSendUpdate) {
    btnSendUpdate.addEventListener('click', async () => {
        const updateChannelSelect = safeElem('update-channel-select');
        const channelId = updateChannelSelect ? updateChannelSelect.value : '';
        const productName = updateProductInput ? updateProductInput.value.trim() : '';
        const content = updateDescInput ? updateDescInput.value.trim() : '';
        const imageInp = safeElem('update-image-input');
        const imageUrl = imageInp ? imageInp.value.trim() : '';

        if (!channelId || !productName || !content) {
            return showToast('⚠️ يرجى اختيار الروم وكتابة اسم المنتج وتفاصيل التحديث!');
        }

        const payload = {
            channel_id: channelId,
            product_name: productName,
            content: content,
            image_url: imageUrl
        };

        try {
            showToast('⏳ جاري نشر التحديث في الديسكورد...');
            const res = await fetch('/api/update/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const result = await res.json();
            if (result.status === 'ok') {
                showToast('✅ تم نشر التحديث بنجاح مع لوقو المتجر!');
                if (updateProductInput) updateProductInput.value = '';
                if (updateDescInput) updateDescInput.value = '';
            } else {
                showToast('❌ خطأ: ' + result.message);
            }
        } catch (e) {
            showToast('❌ تعذر النشر: ' + e.message);
        }
    });
}

// [[ Publish Rules to Discord ]] //
const btnSendRules = safeElem('btn-send-rules');
if (btnSendRules) {
    btnSendRules.addEventListener('click', async () => {
        const rulesSelect = safeElem('rules-channel-select');
        const channelId = rulesSelect ? rulesSelect.value : '';
        const title = rulesTitleInput ? rulesTitleInput.value.trim() : '';
        const subtitle = rulesSubtitleInput ? rulesSubtitleInput.value.trim() : '';
        const rulesText = rulesTextInput ? rulesTextInput.value.trim() : '';
        const color = rulesColorInput ? rulesColorInput.value : '#00ff41';
        const includeBanner = rulesBannerCheckbox ? rulesBannerCheckbox.checked : true;

        if (!channelId || !rulesText) {
            return showToast('⚠️ يرجى اختيار الروم وكتابة بنود القوانين!');
        }

        const payload = {
            channel_id: channelId,
            title: title,
            subtitle: subtitle,
            rules_text: rulesText,
            color: color,
            include_banner: includeBanner
        };

        try {
            showToast('⏳ جاري نشر القوانين في الديسكورد...');
            const res = await fetch('/api/rules/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const result = await res.json();
            if (result.status === 'ok') {
                showToast('✅ تم نشر القوانين بنجاح بتصميم مودرن وفخم!');
            } else {
                showToast('❌ خطأ: ' + result.message);
            }
        } catch (e) {
            showToast('❌ تعذر النشر: ' + e.message);
        }
    });
}

// [[ Save Settings ]] //
const btnSaveSettings = safeElem('btn-save-settings');
if (btnSaveSettings) {
    btnSaveSettings.addEventListener('click', async () => {
        const tokenInp = safeElem('token-input');
        const staffSelect = safeElem('staff-role-select');
        const staffManual = safeElem('staff-role-id-manual');
        const catSelect = safeElem('ticket-category-select');
        const catManual = safeElem('category-id-manual');
        const closedSelect = safeElem('closed-category-select');
        const closedManual = safeElem('closed-category-id-manual');

        const token = tokenInp ? tokenInp.value.trim() : '';
        const staffRole = (staffSelect && staffSelect.value) || (staffManual ? staffManual.value.trim() : '');
        const category = (catSelect && catSelect.value) || (catManual ? catManual.value.trim() : '');
        const closedCategory = (closedSelect && closedSelect.value) || (closedManual ? closedManual.value.trim() : '');

        const payload = {
            token: token,
            staff_role_id: staffRole,
            ticket_category_id: category,
            closed_category_id: closedCategory
        };

        try {
            showToast('💾 جاري حفظ الإعدادات...');
            const res = await fetch('/api/config/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const result = await res.json();
            if (result.status === 'ok') {
                showToast('✅ تم حفظ الإعدادات بنجاح! يتم الآن ربط البوت...');
                setTimeout(loadStatus, 2000);
            }
        } catch (e) {
            showToast('❌ خطأ في الحفظ: ' + e.message);
        }
    });
}

// Toggle Token Visibility
const toggleTokenBtn = safeElem('toggle-token-btn');
const tokenInput = safeElem('token-input');
if (toggleTokenBtn && tokenInput) {
    toggleTokenBtn.addEventListener('click', () => {
        if (tokenInput.type === 'password') {
            tokenInput.type = 'text';
            toggleTokenBtn.innerText = 'إخفاء';
        } else {
            tokenInput.type = 'password';
            toggleTokenBtn.innerText = 'إظهار';
        }
    });
}

// Toast Utility
function showToast(msg) {
    const toast = safeElem('toast');
    const toastMsg = safeElem('toast-msg');
    if (toast && toastMsg) {
        toastMsg.innerText = msg;
        toast.classList.remove('hidden');
        setTimeout(() => {
            toast.classList.add('hidden');
        }, 4000);
    }
}

// Initial Load & Auto Poll
document.addEventListener('DOMContentLoaded', () => {
    loadStatus();
    setInterval(loadStatus, 5000);
});
if (document.readyState === 'complete' || document.readyState === 'interactive') {
    loadStatus();
}
