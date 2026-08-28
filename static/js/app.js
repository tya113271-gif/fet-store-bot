// [[ State & DOM References ]] //
let currentConfig = {};
let botData = {};

// Elements
const botStatusDot = document.querySelector('.status-dot');
const botStatusText = document.getElementById('bot-status-text');
const botProfileCard = document.getElementById('bot-profile-card');
const botUsername = document.getElementById('bot-username');
const botAvatar = document.getElementById('bot-avatar');

// Navigation Tabs
document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
        btn.classList.add('active');
        const tabId = btn.dataset.tab;
        document.getElementById(tabId).classList.add('active');
    });
});

// [[ Live Preview Sync - Ticket Panel ]] //
const ticketTitleInput = document.getElementById('ticket-title-input');
const ticketDescInput = document.getElementById('ticket-desc-input');
const ticketPlaceholderInput = document.getElementById('ticket-placeholder-input');
const ticketColorInput = document.getElementById('ticket-color-input');

const previewTitle = document.getElementById('preview-title');
const previewDesc = document.getElementById('preview-desc');
const previewSelectPlaceholder = document.getElementById('preview-select-placeholder');
const previewEmbed = document.getElementById('preview-embed');

ticketTitleInput.addEventListener('input', (e) => {
    previewTitle.innerText = e.target.value || 'FET STORE - Support & Ticket System';
});

ticketDescInput.addEventListener('input', (e) => {
    previewDesc.innerHTML = (e.target.value || '').replace(/\n/g, '<br>');
});

ticketPlaceholderInput.addEventListener('input', (e) => {
    previewSelectPlaceholder.innerText = e.target.value || '📂 - اختر نوع الخدمة المطلوبة';
});

ticketColorInput.addEventListener('input', (e) => {
    previewEmbed.style.borderLeftColor = e.target.value;
});

// [[ Live Preview Sync - Updates Broadcaster ]] //
const updateProductInput = document.getElementById('update-product-input');
const updateDescInput = document.getElementById('update-desc-input');
const previewUpdateTitle = document.getElementById('preview-update-title');
const previewUpdateDesc = document.getElementById('preview-update-desc');

updateProductInput.addEventListener('input', (e) => {
    const val = e.target.value.trim();
    previewUpdateTitle.innerText = val ? `🚀 تم تحديث المنتج: ${val}` : '🚀 تم تحديث المنتج: FET INVENTORY V1.0';
});

updateDescInput.addEventListener('input', (e) => {
    previewUpdateDesc.innerHTML = (e.target.value || '').replace(/\n/g, '<br>');
});

// [[ API - Fetch Bot Status & Channels ]] //
async function loadStatus() {
    try {
        const res = await fetch('/api/status');
        const data = await res.json();
        botData = data;
        currentConfig = data.config || {};

        if (data.online) {
            botStatusDot.className = 'status-dot online';
            botStatusText.innerText = 'البوت متصل بنجاح 🟢';
            botProfileCard.classList.remove('hidden');
            botUsername.innerText = data.bot_user;
            if (data.bot_avatar) botAvatar.src = data.bot_avatar;
        } else {
            botStatusDot.className = 'status-dot offline';
            botStatusText.innerText = 'البوت غير متصل 🔴 (يرجى إدخال التوكن)';
            botProfileCard.classList.add('hidden');
        }

        // Fill channels & roles dropdowns
        populateDropdowns(data.guilds || []);
        
        // Fill initial inputs with config
        if (currentConfig.token) {
            document.getElementById('token-input').value = currentConfig.token;
        }
        if (currentConfig.staff_role_id) {
            document.getElementById('staff-role-id-manual').value = currentConfig.staff_role_id;
        }
        if (currentConfig.ticket_category_id) {
            document.getElementById('category-id-manual').value = currentConfig.ticket_category_id;
        }
        if (currentConfig.closed_category_id) {
            document.getElementById('closed-category-id-manual').value = currentConfig.closed_category_id;
        }

    } catch (e) {
        console.error('Error fetching status:', e);
    }
}

function populateDropdowns(guilds) {
    const ticketChannelSelect = document.getElementById('ticket-channel-select');
    const updateChannelSelect = document.getElementById('update-channel-select');
    const staffRoleSelect = document.getElementById('staff-role-select');
    const categorySelect = document.getElementById('ticket-category-select');
    const closedCategorySelect = document.getElementById('closed-category-select');

    ticketChannelSelect.innerHTML = '<option value="">-- اختر الروم من سيرفرك --</option>';
    updateChannelSelect.innerHTML = '<option value="">-- اختر الروم --</option>';
    staffRoleSelect.innerHTML = '<option value="">-- اختر الرتبة التي تستقبل التكتات --</option>';
    categorySelect.innerHTML = '<option value="">-- اختر قسم التكتات الفعالة (تكتات فعالة) --</option>';
    if (closedCategorySelect) {
        closedCategorySelect.innerHTML = '<option value="">-- اختر قسم التكتات المغلقة (تكتات مغلقة) --</option>';
    }

    guilds.forEach(g => {
        // Text Channels
        if (g.channels) {
            g.channels.forEach(ch => {
                const opt1 = new Option(`# ${ch.name} (${g.name})`, ch.id);
                const opt2 = new Option(`# ${ch.name} (${g.name})`, ch.id);
                ticketChannelSelect.add(opt1);
                updateChannelSelect.add(opt2);
            });
        }
        // Roles
        if (g.roles) {
            g.roles.forEach(r => {
                const opt = new Option(`@${r.name}`, r.id);
                staffRoleSelect.add(opt);
            });
        }
        // Categories
        if (g.categories) {
            g.categories.forEach(cat => {
                const opt1 = new Option(`📁 ${cat.name}`, cat.id);
                const opt2 = new Option(`📁 ${cat.name}`, cat.id);
                categorySelect.add(opt1);
                if (closedCategorySelect) closedCategorySelect.add(opt2);
            });
        }
    });
}

// [[ Send Ticket Panel to Discord ]] //
document.getElementById('btn-send-ticket').addEventListener('click', async () => {
    const channelId = document.getElementById('ticket-channel-select').value;
    if (!channelId) {
        return showToast('⚠️ يرجى اختيار الروم أولاً!');
    }

    const payload = {
        channel_id: channelId,
        title: ticketTitleInput.value,
        description: ticketDescInput.value,
        placeholder: ticketPlaceholderInput.value,
        color: ticketColorInput.value
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

// [[ Publish Product Update to Discord ]] //
document.getElementById('btn-send-update').addEventListener('click', async () => {
    const channelId = document.getElementById('update-channel-select').value;
    const productName = updateProductInput.value.trim();
    const content = updateDescInput.value.trim();
    const imageUrl = document.getElementById('update-image-input').value.trim();

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
            updateProductInput.value = '';
            updateDescInput.value = '';
        } else {
            showToast('❌ خطأ: ' + result.message);
        }
    } catch (e) {
        showToast('❌ تعذر النشر: ' + e.message);
    }
});

// [[ Save Settings ]] //
document.getElementById('btn-save-settings').addEventListener('click', async () => {
    const token = document.getElementById('token-input').value.trim();
    const staffRole = document.getElementById('staff-role-select').value || document.getElementById('staff-role-id-manual').value.trim();
    const category = document.getElementById('ticket-category-select').value || document.getElementById('category-id-manual').value.trim();
    const closedCategory = (document.getElementById('closed-category-select') ? document.getElementById('closed-category-select').value : '') || document.getElementById('closed-category-id-manual').value.trim();

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

// Toggle Token Visibility
const toggleTokenBtn = document.getElementById('toggle-token-btn');
const tokenInput = document.getElementById('token-input');
toggleTokenBtn.addEventListener('click', () => {
    if (tokenInput.type === 'password') {
        tokenInput.type = 'text';
        toggleTokenBtn.innerText = 'إخفاء';
    } else {
        tokenInput.type = 'password';
        toggleTokenBtn.innerText = 'إظهار';
    }
});

// Toast Utility
function showToast(msg) {
    const toast = document.getElementById('toast');
    const toastMsg = document.getElementById('toast-msg');
    toastMsg.innerText = msg;
    toast.classList.remove('hidden');
    setTimeout(() => {
        toast.classList.add('hidden');
    }, 4000);
}

// Initial Load & Auto Poll
loadStatus();
setInterval(loadStatus, 5000);
