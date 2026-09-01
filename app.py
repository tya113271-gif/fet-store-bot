import os
import re
import sys
import json
import asyncio
import threading
import logging

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("FET_DASHBOARD")

from flask import Flask, render_template_string, render_template, request, jsonify, Response
import discord
from discord.ext import commands

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "data", "config.json")
ASSETS_DIR = os.path.join(BASE_DIR, "static", "img")

def load_config():
    cfg = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except:
            cfg = {}
            
    env_token = os.environ.get("DISCORD_TOKEN") or os.environ.get("BOT_TOKEN")
    if env_token:
        cfg["token"] = env_token.strip()
        
    return cfg

def save_config(cfg):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)

# [[ Flask Web Dashboard ]] #
app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["SECRET_KEY"] = "fet_store_secret_2026"

# [[ Discord Bot Setup ]] #
intents = discord.Intents.default()
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot_error_msg = None
bot_thread_active = False

def is_user_staff(member: discord.Member, guild: discord.Guild, staff_role_id):
    if member.guild_permissions.administrator or member.guild_permissions.manage_channels:
        return True
    if staff_role_id:
        try:
            role = guild.get_role(int(staff_role_id))
            if role and role in member.roles:
                return True
        except:
            pass
    for r in member.roles:
        r_name = r.name.lower()
        if any(kw in r_name for kw in ["admin", "staff", "owner", "support", "إدارة", "مسؤول", "دعم", "صاحب"]):
            return True
    return False

def get_target_category(guild, cat_id_key, search_keywords):
    cfg = load_config()
    configured_id = cfg.get(cat_id_key)
    if configured_id:
        try:
            cat = guild.get_channel(int(configured_id))
            if cat and isinstance(cat, discord.CategoryChannel):
                return cat
        except:
            pass
            
    for cat in guild.categories:
        for kw in search_keywords:
            if kw.lower() in cat.name.lower():
                return cat
    return None

# [[ UI Views for Closed Tickets ]] #
class ClosedTicketActionView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="حذف نهائي (Delete Ticket)", style=discord.ButtonStyle.danger, custom_id="fet_delete_ticket_btn", emoji="🗑️")
    async def delete_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = load_config()
        if not is_user_staff(interaction.user, interaction.guild, cfg.get("staff_role_id")):
            await interaction.response.send_message("❌ عذراً، حذف التذكرة متاح فقط لطاقم الإدارة والدعم الفني.", ephemeral=True)
            return

        await interaction.response.send_message("⚠️ جاري حذف التذكرة نهائياً خلال 3 ثوانٍ...", ephemeral=False)
        await asyncio.sleep(3)
        try:
            await interaction.channel.delete(reason=f"Permanently deleted by {interaction.user}")
        except Exception as e:
            logger.error(f"Error deleting channel: {e}")

    @discord.ui.button(label="إعادة فتح (Re-open Ticket)", style=discord.ButtonStyle.success, custom_id="fet_reopen_ticket_btn", emoji="🔓")
    async def reopen_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = load_config()
        if not is_user_staff(interaction.user, interaction.guild, cfg.get("staff_role_id")):
            await interaction.response.send_message("❌ عذراً، إعادة فتح التذكرة متاح فقط لطاقم الإدارة.", ephemeral=True)
            return

        guild = interaction.guild
        channel = interaction.channel
        
        owner_id = None
        if channel.topic:
            match = re.search(r"ID:\s*(\d+)", channel.topic)
            if match:
                owner_id = int(match.group(1))

        if owner_id:
            owner_member = guild.get_member(owner_id)
            if owner_member:
                await channel.set_permissions(owner_member, overwrite=discord.PermissionOverwrite(
                    view_channel=True,
                    read_messages=True,
                    send_messages=True,
                    read_message_history=True,
                    attach_files=True,
                    embed_links=True
                ))
        else:
            for target in list(channel.overwrites.keys()):
                if isinstance(target, discord.Member) and not target.bot:
                    await channel.set_permissions(target, overwrite=discord.PermissionOverwrite(
                        view_channel=True,
                        read_messages=True,
                        send_messages=True,
                        read_message_history=True,
                        attach_files=True,
                        embed_links=True
                    ))
        
        active_cat = get_target_category(guild, "ticket_category_id", ["فعال", "active", "تكتات فعالة", "open"])
        new_name = channel.name.replace("closed-", "ticket-").replace("مغلق-", "ticket-")
        try:
            if active_cat:
                await channel.edit(category=active_cat, name=new_name)
            else:
                await channel.edit(name=new_name)
        except Exception as e:
            logger.error(f"Error reopening channel: {e}")
            
        await interaction.response.send_message(f"🔓 تم إعادة فتح التذكرة بنجاح بواسطة {interaction.user.mention} وإعادة صلاحيات المشاهدة للعميل!", view=CloseTicketView())

# [[ UI View for Active Tickets ]] #
class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="إغلاق التذكرة (Close Ticket)", style=discord.ButtonStyle.danger, custom_id="fet_close_ticket_btn", emoji="🔒")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        channel = interaction.channel
        user = interaction.user
        cfg = load_config()
        staff_role_id = cfg.get("staff_role_id")

        if not is_user_staff(user, guild, staff_role_id):
            await interaction.response.send_message("❌ عذراً، إغلاق التذكرة متاح فقط لطاقم الإدارة والدعم الفني.", ephemeral=True)
            return

        await interaction.response.send_message(f"🔒 تم إغلاق التذكرة بواسطة {user.mention}. تم سحب صلاحية المشاهدة من العميل ونقل التذكرة إلى قسم التكتات المغلقة (للإدارة فقط).", ephemeral=False)
        
        staff_role = guild.get_role(int(staff_role_id)) if staff_role_id else None

        # Move to Closed Category
        closed_cat = get_target_category(guild, "closed_category_id", ["مغلق", "closed", "تكتات مغلقة", "archive"])
        new_name = channel.name.replace("ticket-", "closed-")
        if not new_name.startswith("closed-"):
            new_name = f"closed-{new_name[:20]}"
            
        try:
            if closed_cat:
                await channel.edit(category=closed_cat, name=new_name, sync_permissions=False)
            else:
                await channel.edit(name=new_name)
        except Exception as e:
            logger.error(f"Error moving ticket channel: {e}")

        # Lock @everyone on this channel
        try:
            await channel.set_permissions(guild.default_role, overwrite=discord.PermissionOverwrite(
                view_channel=False,
                read_messages=False,
                send_messages=False,
                read_message_history=False
            ))
        except Exception as e:
            logger.error(f"Error locking default role: {e}")

        # Explicitly deny all non-staff members in overwrites
        for target in list(channel.overwrites.keys()):
            if isinstance(target, discord.Member) and not target.bot:
                if not is_user_staff(target, guild, staff_role_id):
                    try:
                        await channel.set_permissions(target, overwrite=discord.PermissionOverwrite(
                            view_channel=False,
                            read_messages=False,
                            send_messages=False,
                            read_message_history=False
                        ))
                    except Exception as e:
                        logger.error(f"Error locking member overwrite: {e}")

        # Explicitly deny all non-staff members currently in channel.members
        for m in list(channel.members):
            if not m.bot and not is_user_staff(m, guild, staff_role_id):
                try:
                    await channel.set_permissions(m, overwrite=discord.PermissionOverwrite(
                        view_channel=False,
                        read_messages=False,
                        send_messages=False,
                        read_message_history=False
                    ))
                except Exception as e:
                    logger.error(f"Error locking member: {e}")

        # Extract ticket owner by ID from topic and deny
        if channel.topic:
            match = re.search(r"ID:\s*(\d+)", channel.topic)
            if match:
                owner_id = int(match.group(1))
                owner_member = guild.get_member(owner_id)
                if owner_member and not is_user_staff(owner_member, guild, staff_role_id):
                    try:
                        await channel.set_permissions(owner_member, overwrite=discord.PermissionOverwrite(
                            view_channel=False,
                            read_messages=False,
                            send_messages=False,
                            read_message_history=False
                        ))
                    except Exception as e:
                        logger.error(f"Error locking owner: {e}")

        # Ensure Staff Role retains full view permissions
        if staff_role:
            try:
                await channel.set_permissions(staff_role, overwrite=discord.PermissionOverwrite(
                    view_channel=True,
                    read_messages=True,
                    send_messages=True,
                    attach_files=True,
                    read_message_history=True
                ))
            except Exception as e:
                logger.error(f"Error setting staff role permissions: {e}")

        # Send closed action panel
        embed = discord.Embed(
            title="🔒 تم إغلاق التذكرة | FET STORE",
            description=f"تم إغلاق التذكرة بنجاح وسحب صلاحية المشاهدة من العميل.\n\n"
                        f"• **الروم أصبحت مخفية تماماً عن العميل ومرئية للإدارة فقط**.\n"
                        f"• تم الإغلاق بواسطة: {user.mention}\n"
                        f"• يمكنك إعادة فتح التذكرة للعميل أو حذفها نهائياً عبر الأزرار أدناه.",
            color=discord.Color.from_str("#ff4757")
        )
        await channel.send(embed=embed, view=ClosedTicketActionView())

class TicketDropdown(discord.ui.Select):
    def __init__(self, placeholder="📂 - اختر نوع الخدمة المطلوبة"):
        options = [
            discord.SelectOption(label="شراء منتج", emoji="🛒", value="buy"),
            discord.SelectOption(label="استفسار", emoji="❓", value="inquiry"),
            discord.SelectOption(label="طلب سكربت خاص", emoji="💎", value="custom_script"),
        ]
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options, custom_id="fet_ticket_dropdown")

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        user = interaction.user
        selected_value = self.values[0]
        
        service_titles = {
            "buy": "شراء منتج",
            "inquiry": "استفسار",
            "custom_script": "طلب سكربت خاص"
        }
        service_name = service_titles.get(selected_value, selected_value)
        
        cfg = load_config()
        staff_role_id = int(cfg.get("staff_role_id")) if cfg.get("staff_role_id") else None
        staff_role = guild.get_role(staff_role_id) if staff_role_id else None
        
        active_cat = get_target_category(guild, "ticket_category_id", ["فعال", "active", "تكتات فعالة", "open"])
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False, read_messages=False, send_messages=False),
            user: discord.PermissionOverwrite(view_channel=True, read_messages=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, read_messages=True, send_messages=True, manage_channels=True)
        }
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, read_messages=True, send_messages=True, attach_files=True, read_message_history=True)

        channel_name = f"ticket-{user.name.lower()[:15]}"
        ticket_channel = await guild.create_text_channel(
            name=channel_name,
            category=active_cat,
            overwrites=overwrites,
            topic=f"Ticket for {user} (ID: {user.id}) | Reason: {service_name}"
        )

        embed = discord.Embed(
            title=f"🎫 تذكرة جديدة: {service_name} | FET STORE",
            description=f"مرحباً بك {user.mention} في الدعم الفني لمتجر **FET STORE**!\n\n"
                        f"• **نوع الخدمة:** `{service_name}`\n"
                        f"• تفضل بكتابة طلبك أو استفسارك بالتفصيل وسيقوم فريقنا بالرد عليك بأسرع وقت.",
            color=discord.Color.from_str(cfg.get("ticket_color", "#00ff41"))
        )
        logo_path = os.path.join(ASSETS_DIR, "logo.png")
        if os.path.exists(logo_path):
            file = discord.File(logo_path, filename="logo.png")
            embed.set_thumbnail(url="attachment://logo.png")
            embed.set_footer(text="FET STORE | Official Support System", icon_url="attachment://logo.png")
            await ticket_channel.send(content=f"{user.mention} | طاقم الدعم جاهز لمساعدتك", embed=embed, file=file, view=CloseTicketView())
        else:
            embed.set_footer(text="FET STORE | Official Support System")
            await ticket_channel.send(content=f"{user.mention} | طاقم الدعم جاهز لمساعدتك", embed=embed, view=CloseTicketView())

        await interaction.response.send_message(f"✅ تم فتح تذكرتك بنجاح في: {ticket_channel.mention}", ephemeral=True)

class TicketPanelView(discord.ui.View):
    def __init__(self, placeholder="📂 - اختر نوع الخدمة المطلوبة"):
        super().__init__(timeout=None)
        self.add_item(TicketDropdown(placeholder=placeholder))

@bot.event
async def on_ready():
    global bot_error_msg
    bot_error_msg = None
    logger.info(f"[BOT READY] Logged in as: {bot.user} (ID: {bot.user.id})")
    bot.add_view(TicketPanelView())
    bot.add_view(CloseTicketView())
    bot.add_view(ClosedTicketActionView())
    await bot.change_presence(activity=discord.Game(name="FET STORE | Dashboard Ready"))

# [[ Built-in HTML / UI Templates ]] #
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FET STORE - Bot Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&family=Rajdhani:wght@600;700&display=swap" rel="stylesheet">
    <style>
:root {
    --bg-dark: #0a0d0a;
    --bg-card: #121812;
    --bg-input: #182218;
    --neon-green: #00ff41;
    --neon-glow: rgba(0, 255, 65, 0.35);
    --border-color: rgba(0, 255, 65, 0.25);
    --text-white: #ffffff;
    --text-muted: #8fa08f;
    --danger: #ff4757;
    --discord-bg: #313338;
    --discord-card: #2b2d31;
    --discord-embed-bg: #2b2d31;
    --discord-text: #dbdee1;
    --discord-white: #f2f3f5;
    --discord-select-bg: #232428;
}
* { margin:0; padding:0; box-sizing:border-box; font-family:'Cairo','Rajdhani',sans-serif; }
body { background-color:var(--bg-dark); color:var(--text-white); min-height:100vh; display:flex; flex-direction:column; }
.dashboard-header { background:#0e140e; border-bottom:1.5px solid var(--border-color); padding:16px 32px; display:flex; justify-content:space-between; align-items:center; box-shadow:0 4px 20px rgba(0,0,0,0.5); }
.header-brand { display:flex; align-items:center; gap:16px; }
.brand-logo { width:50px; height:50px; border-radius:50%; border:2px solid var(--neon-green); box-shadow:0 0 15px var(--neon-glow); }
.brand-text h1 { font-size:22px; font-weight:900; letter-spacing:2px; }
.brand-text p { font-size:13px; color:var(--text-muted); }
.accent { color:var(--neon-green); text-shadow:0 0 10px var(--neon-green); }
.header-status { display:flex; align-items:center; gap:16px; }
.status-indicator { display:flex; align-items:center; gap:8px; background:rgba(20,30,20,0.8); border:1px solid var(--border-color); padding:8px 16px; border-radius:20px; font-size:13px; font-weight:700; }
.status-dot { width:10px; height:10px; border-radius:50%; }
.status-dot.online { background:var(--neon-green); box-shadow:0 0 10px var(--neon-green); }
.status-dot.offline { background:var(--danger); box-shadow:0 0 10px var(--danger); }
.bot-info-card { display:flex; align-items:center; gap:10px; background:var(--bg-card); border:1px solid var(--border-color); padding:6px 14px; border-radius:20px; }
.bot-avatar { width:28px; height:28px; border-radius:50%; }
.bot-tag { font-size:13px; font-weight:700; color:var(--neon-green); }
.dashboard-wrapper { display:flex; flex:1; overflow:hidden; }
.dashboard-nav { width:260px; background:#0d120d; border-left:1px solid var(--border-color); padding:24px 16px; display:flex; flex-direction:column; gap:10px; }
.nav-btn { display:flex; align-items:center; gap:12px; background:transparent; border:1px solid transparent; color:var(--text-muted); padding:12px 16px; border-radius:8px; font-size:14px; font-weight:700; cursor:pointer; text-align:right; transition:all 0.2s ease; }
.nav-btn:hover { background:rgba(0,255,65,0.08); color:var(--text-white); border-color:var(--border-color); }
.nav-btn.active { background:rgba(0,255,65,0.15); color:var(--neon-green); border-color:var(--neon-green); box-shadow:0 0 15px rgba(0,255,65,0.2); }
.nav-icon { font-size:18px; }
.dashboard-content { flex:1; padding:30px; overflow-y:auto; }
.tab-pane { display:none; }
.tab-pane.active { display:block; }
.pane-grid { display:grid; grid-template-columns:1fr 1.15fr; gap:24px; }
.panel-card { background:var(--bg-card); border:1px solid var(--border-color); border-radius:12px; padding:24px; box-shadow:0 4px 25px rgba(0,0,0,0.4); }
.card-title { font-size:18px; font-weight:800; margin-bottom:20px; color:var(--text-white); border-bottom:1px solid var(--border-color); padding-bottom:12px; }
.form-group { margin-bottom:18px; }
.form-group label { display:block; font-size:13px; font-weight:700; color:var(--neon-green); margin-bottom:8px; }
.form-input { width:100%; background:var(--bg-input); border:1px solid var(--border-color); border-radius:8px; padding:10px 14px; color:var(--text-white); font-size:14px; outline:none; transition:all 0.2s ease; }
.form-input:focus { border-color:var(--neon-green); box-shadow:0 0 10px var(--neon-glow); }
textarea.form-input { resize:vertical; line-height:1.6; }
.color-picker { width:100%; height:40px; border:1px solid var(--border-color); border-radius:6px; background:transparent; cursor:pointer; }
.btn-primary { width:100%; background:var(--neon-green); color:#040c04; border:none; border-radius:8px; padding:12px 0; font-size:15px; font-weight:800; cursor:pointer; box-shadow:0 0 20px var(--neon-glow); transition:all 0.2s ease; margin-top:10px; }
.btn-primary:hover { background:#ffffff; box-shadow:0 0 25px #ffffff; transform:translateY(-2px); }
.token-wrapper { display:flex; gap:8px; }
.btn-secondary { background:rgba(0,255,65,0.1); color:var(--neon-green); border:1px solid var(--border-color); padding:0 16px; border-radius:6px; cursor:pointer; font-weight:700; }
.form-hint { display:block; color:var(--text-muted); font-size:11px; margin-top:6px; }
.mt-2 { margin-top:8px; }
.discord-preview-box { background:var(--discord-bg); border-radius:8px; padding:20px; direction:ltr; text-align:left; }
.discord-message { display:flex; gap:16px; }
.discord-avatar { width:42px; height:42px; border-radius:50%; flex-shrink:0; }
.discord-content { flex:1; display:flex; flex-direction:column; gap:8px; }
.discord-header { display:flex; align-items:center; gap:8px; }
.bot-name { font-weight:700; color:var(--discord-white); font-size:15px; }
.bot-badge { background:#5865f2; color:#ffffff; font-size:10px; font-weight:700; padding:1px 5px; border-radius:3px; }
.timestamp { font-size:12px; color:#949ba4; }
.discord-embed { background:var(--discord-embed-bg); border-left:4px solid var(--neon-green); border-radius:4px; padding:12px 16px; display:flex; flex-direction:column; gap:10px; max-width:520px; }
.embed-author { display:flex; align-items:center; gap:8px; font-size:13px; font-weight:700; color:var(--discord-white); }
.author-icon { width:20px; height:20px; border-radius:50%; }
.embed-body-flex { display:flex; justify-content:space-between; gap:12px; }
.embed-title { font-size:16px; font-weight:700; color:var(--discord-white); margin-bottom:6px; }
.embed-desc { font-size:13px; color:var(--discord-text); line-height:1.5; white-space:pre-line; }
.embed-thumbnail { width:65px; height:65px; border-radius:50%; object-fit:cover; flex-shrink:0; }
.embed-banner-container { width:100%; border-radius:4px; overflow:hidden; }
.embed-banner { width:100%; display:block; }
.embed-footer { display:flex; align-items:center; gap:8px; font-size:11px; color:#949ba4; padding-top:4px; border-top:1px solid rgba(255,255,255,0.06); }
.footer-icon { width:16px; height:16px; border-radius:50%; }
.discord-select-menu { background:var(--discord-select-bg); border:1px solid rgba(255,255,255,0.1); border-radius:4px; padding:10px 14px; display:flex; justify-content:space-between; align-items:center; color:#949ba4; font-size:14px; font-weight:600; cursor:pointer; max-width:520px; }
.discord-mention-tag { font-size:14px; color:#e0e2e5; margin-bottom:4px; }
.hidden { display:none !important; }
.toast { position:fixed; bottom:30px; left:50%; transform:translateX(-50%); background:#0f1a0f; border:1.5px solid var(--neon-green); box-shadow:0 0 25px var(--neon-glow); padding:12px 28px; border-radius:25px; color:#ffffff; font-weight:700; z-index:1000; animation:toastUp 0.25s ease; }
@keyframes toastUp { from { opacity:0; transform:translate(-50%,20px); } to { opacity:1; transform:translate(-50%,0); } }
    </style>
</head>
<body>
    <header class="dashboard-header">
        <div class="header-brand">
            <img src="/static/img/logo.png" alt="FET STORE Logo" class="brand-logo" onerror="this.src='https://cdn.discordapp.com/embed/avatars/0.png'">
            <div class="brand-text">
                <h1>FET <span class="accent">STORE</span></h1>
                <p>لوحة التحكم بالبوت ونظام التكتات والتحديثات والقوانين</p>
            </div>
        </div>
        <div class="header-status">
            <div class="status-indicator" id="bot-status-badge">
                <span class="status-dot offline"></span>
                <span class="status-text" id="bot-status-text">جاري فحص الاتصال...</span>
            </div>
            <div class="bot-info-card hidden" id="bot-profile-card">
                <img src="/static/img/logo.png" id="bot-avatar" class="bot-avatar" onerror="this.src='https://cdn.discordapp.com/embed/avatars/0.png'">
                <span class="bot-tag" id="bot-username">FET Store Bot</span>
            </div>
        </div>
    </header>

    <div class="dashboard-wrapper">
        <aside class="dashboard-nav">
            <button class="nav-btn active" data-tab="ticket-tab">
                <span class="nav-icon">🎟️</span>
                <span class="nav-title">لوحة التذاكر (Tickets)</span>
            </button>
            <button class="nav-btn" data-tab="updates-tab">
                <span class="nav-icon">📢</span>
                <span class="nav-title">نشر التحديثات (Updates)</span>
            </button>
            <button class="nav-btn" data-tab="rules-tab">
                <span class="nav-icon">📜</span>
                <span class="nav-title">نشر القوانين (Rules)</span>
            </button>
            <button class="nav-btn" data-tab="settings-tab">
                <span class="nav-icon">⚙️</span>
                <span class="nav-title">إعدادات البوت والربط</span>
            </button>
        </aside>

        <main class="dashboard-content">
            <!-- Tab 1: Ticket Panel -->
            <section class="tab-pane active" id="ticket-tab">
                <div class="pane-grid">
                    <div class="panel-card form-card">
                        <h2 class="card-title">⚙️ تخصيص رسالة التكت</h2>
                        <div class="form-group">
                            <label>📍 الروم المراد إرسال التكت فيها:</label>
                            <select id="ticket-channel-select" class="form-input">
                                <option value="">-- اختر الروم من سيرفرك --</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label>📝 عنوان الرسالة (Embed Title):</label>
                            <input type="text" id="ticket-title-input" class="form-input" value="FET STORE - Support & Ticket System">
                        </div>
                        <div class="form-group">
                            <label>📄 وصف التكت (Description):</label>
                            <textarea id="ticket-desc-input" class="form-input" rows="6">عزيزي العضو / Dear Member

من خلال هذه القائمة يمكنك:
• اختيار القسم المناسب لفتح تذكرة دعم فني
• سيتم إنشاء روم خاصة بك مع طاقم الدعم
• سيقوم فريقنا بالرد عليك في أسرع وقت ممكن</textarea>
                        </div>
                        <div class="form-group">
                            <label>📂 النص الظاهر بقائمة الاختيار (Dropdown Placeholder):</label>
                            <input type="text" id="ticket-placeholder-input" class="form-input" value="📂 - اختر نوع الخدمة المطلوبة">
                        </div>
                        <div class="form-group">
                            <label>🎨 لون الإطار (Hex Color):</label>
                            <input type="color" id="ticket-color-input" class="color-picker" value="#00ff41">
                        </div>
                        <button id="btn-send-ticket" class="btn-primary">
                            <span>🚀 إرسال / تحديث التكت في الديسكورد</span>
                        </button>
                    </div>

                    <div class="panel-card preview-card">
                        <h2 class="card-title">👁️ معاينة حية في الديسكورد</h2>
                        <div class="discord-preview-box">
                            <div class="discord-message">
                                <img src="/static/img/logo.png" class="discord-avatar" onerror="this.src='https://cdn.discordapp.com/embed/avatars/0.png'">
                                <div class="discord-content">
                                    <div class="discord-header">
                                        <span class="bot-name">FET STORE BOT</span>
                                        <span class="bot-badge">APP</span>
                                        <span class="timestamp">Today at 11:45 PM</span>
                                    </div>
                                    <div class="discord-embed" id="preview-embed" style="border-left-color: #00ff41;">
                                        <div class="embed-author">
                                            <img src="/static/img/logo.png" class="author-icon" onerror="this.src='https://cdn.discordapp.com/embed/avatars/0.png'">
                                            <span id="preview-author-text">FET STORE - Official Ticket System</span>
                                        </div>
                                        <div class="embed-body-flex">
                                            <div class="embed-text-col">
                                                <h3 class="embed-title" id="preview-title">FET STORE - Support & Ticket System</h3>
                                                <div class="embed-desc" id="preview-desc">
                                                    عزيزي العضو / Dear Member<br><br>
                                                    من خلال هذه القائمة يمكنك:<br>
                                                    • اختيار القسم المناسب لفتح تذكرة دعم فني<br>
                                                    • سيتم إنشاء روم خاصة بك مع طاقم الدعم<br>
                                                    • سيقوم فريقنا بالرد عليك في أسرع وقت ممكن
                                                </div>
                                            </div>
                                            <img src="/static/img/logo.png" class="embed-thumbnail" onerror="this.src='https://cdn.discordapp.com/embed/avatars/0.png'">
                                        </div>
                                        <div class="embed-banner-container">
                                            <img src="/static/img/ticket_banner.png" class="embed-banner" onerror="this.style.display='none'">
                                        </div>
                                        <div class="embed-footer">
                                            <img src="/static/img/logo.png" class="footer-icon" onerror="this.src='https://cdn.discordapp.com/embed/avatars/0.png'">
                                            <span>FET STORE | Best Quality Products</span>
                                        </div>
                                    </div>
                                    <div class="discord-select-menu">
                                        <span class="select-text" id="preview-select-placeholder">📂 - اختر نوع الخدمة المطلوبة</span>
                                        <span class="select-arrow">▼</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            <!-- Tab 2: Updates -->
            <section class="tab-pane" id="updates-tab">
                <div class="pane-grid">
                    <div class="panel-card form-card">
                        <h2 class="card-title">📢 نشر تحديث منتج جديد</h2>
                        <div class="form-group">
                            <label>📍 الروم المراد نشر التحديث فيها (روم التحديثات):</label>
                            <select id="update-channel-select" class="form-input">
                                <option value="">-- اختر الروم --</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label>🏷️ اسم المنتج أو السكربت المحدث:</label>
                            <input type="text" id="update-product-input" class="form-input" placeholder="مثال: CAMRY 2024 V2 أو FET INVENTORY V1.0">
                        </div>
                        <div class="form-group">
                            <label>📋 تفاصيل ومميزات التحديث (Changelog):</label>
                            <textarea id="update-desc-input" class="form-input" rows="6" placeholder="• تم إصلاح مشكلة الأسلحة
• تم إضافة وزنيات جديدة وسريعة
• تحسين الأداء بنسبة 50%..."></textarea>
                        </div>
                        <div class="form-group">
                            <label>🖼️ رابط صورة المنتج (اختياري):</label>
                            <input type="text" id="update-image-input" class="form-input" placeholder="https://example.com/product.png">
                        </div>
                        <button id="btn-send-update" class="btn-primary">
                            <span>📢 نشر التحديث إلى الديسكورد فوراً</span>
                        </button>
                    </div>

                    <div class="panel-card preview-card">
                        <h2 class="card-title">👁️ معاينة رسالة التحديث في الديسكورد</h2>
                        <div class="discord-preview-box">
                            <div class="discord-message">
                                <img src="/static/img/logo.png" class="discord-avatar" onerror="this.src='https://cdn.discordapp.com/embed/avatars/0.png'">
                                <div class="discord-content">
                                    <div class="discord-header">
                                        <span class="bot-name">FET STORE BOT</span>
                                        <span class="bot-badge">APP</span>
                                        <span class="timestamp">Today at 11:50 PM</span>
                                    </div>
                                    <div class="discord-mention-tag">@everyone 📢 تحديث جديد في متجر <strong>FET STORE</strong></div>
                                    <div class="discord-embed" style="border-left-color: #00ff41;">
                                        <div class="embed-body-flex">
                                            <div class="embed-text-col">
                                                <h3 class="embed-title" id="preview-update-title">🚀 تم تحديث المنتج: FET INVENTORY V1.0</h3>
                                                <div class="embed-desc" id="preview-update-desc">
                                                    • تم إضافة نظام الأسلحة التلقائي<br>
                                                    • تحسين واجهة المستخدم باللون الأخضر النيون<br>
                                                    • دعم كامل للسحب والإفلات
                                                </div>
                                            </div>
                                            <img src="/static/img/logo.png" class="embed-thumbnail" onerror="this.src='https://cdn.discordapp.com/embed/avatars/0.png'">
                                        </div>
                                        <div class="embed-footer">
                                            <img src="/static/img/logo.png" class="footer-icon" onerror="this.src='https://cdn.discordapp.com/embed/avatars/0.png'">
                                            <span>FET STORE | New Update Released</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            <!-- Tab 3: Rules Broadcaster -->
            <section class="tab-pane" id="rules-tab">
                <div class="pane-grid">
                    <div class="panel-card form-card">
                        <h2 class="card-title">📜 نشر وتخصيص قوانين السيرفر</h2>
                        <div class="form-group">
                            <label>📍 الروم المراد نشر القوانين فيها (روم القوانين):</label>
                            <select id="rules-channel-select" class="form-input">
                                <option value="">-- اختر الروم --</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label>🏷️ عنوان رسالة القوانين (Embed Title):</label>
                            <input type="text" id="rules-title-input" class="form-input" value="📜 قوانين وشروط متجر FET STORE الرسمية">
                        </div>
                        <div class="form-group">
                            <label>📝 المقدمة / الترحيب (Introduction):</label>
                            <input type="text" id="rules-subtitle-input" class="form-input" value="نرجو من جميع الأعضاء والعملاء الكرام الالتزام بالتعليمات التالية لضمان أفضل تجربة:">
                        </div>
                        <div class="form-group">
                            <label>📋 بنود القوانين (سطر تحت الثاني):</label>
                            <textarea id="rules-text-input" class="form-input" rows="10">🔹 1. الاحترام المتبادل بين الأعضاء وطاقم الإدارة وعدم إثارة المشاكل.
🔹 2. يمنع الإعلان لروابط أو متاجر خارجية داخل السيرفر أو بالخاص منعاً باتاً.
🔹 3. يمنع فتح التكت بدون سبب أو تكرار المنشن للإدارة.
🔹 4. جميع المعاملات المالية والشراء تتم حصراً عبر التكتات الرسمية فقط.
🔹 5. يمنع نشر محتوى غير لائق أو سبام داخل الشات العام.
🔹 6. عند مواجهة أي مشكلة في طلبك، يرجى التوجه لتكت الدعم الفني فوراً.</textarea>
                        </div>
                        <div class="form-group">
                            <label>🎨 لون الإطار (Hex Color):</label>
                            <input type="color" id="rules-color-input" class="color-picker" value="#00ff41">
                        </div>
                        <div class="form-group" style="display:flex; align-items:center; gap:8px;">
                            <input type="checkbox" id="rules-banner-checkbox" checked style="accent-color: var(--neon-green); width:18px; height:18px;">
                            <label for="rules-banner-checkbox" style="margin:0; cursor:pointer;">إرفاق بنر المتجر الرسمي بأسفل الرسالة</label>
                        </div>
                        <button id="btn-send-rules" class="btn-primary">
                            <span>📜 نشر القوانين إلى الديسكورد فوراً</span>
                        </button>
                    </div>

                    <div class="panel-card preview-card">
                        <h2 class="card-title">👁️ معاينة حية لرسالة القوانين في الديسكورد</h2>
                        <div class="discord-preview-box">
                            <div class="discord-message">
                                <img src="/static/img/logo.png" class="discord-avatar" onerror="this.src='https://cdn.discordapp.com/embed/avatars/0.png'">
                                <div class="discord-content">
                                    <div class="discord-header">
                                        <span class="bot-name">FET STORE BOT</span>
                                        <span class="bot-badge">APP</span>
                                        <span class="timestamp">Today at 10:00 PM</span>
                                    </div>
                                    <div class="discord-embed" id="preview-rules-embed" style="border-left-color: #00ff41;">
                                        <div class="embed-author">
                                            <img src="/static/img/logo.png" class="author-icon" onerror="this.src='https://cdn.discordapp.com/embed/avatars/0.png'">
                                            <span>FET STORE | Official Guidelines</span>
                                        </div>
                                        <div class="embed-body-flex">
                                            <div class="embed-text-col">
                                                <h3 class="embed-title" id="preview-rules-title">📜 قوانين وشروط متجر FET STORE الرسمية</h3>
                                                <div class="embed-desc" id="preview-rules-desc">
                                                    نرجو من جميع الأعضاء والعملاء الكرام الالتزام بالتعليمات التالية لضمان أفضل تجربة:<br><br>
                                                    🔹 1. الاحترام المتبادل بين الأعضاء وطاقم الإدارة وعدم إثارة المشاكل.<br>
                                                    🔹 2. يمنع الإعلان لروابط أو متاجر خارجية داخل السيرفر أو بالخاص منعاً باتاً.<br>
                                                    🔹 3. يمنع فتح التكت بدون سبب أو تكرار المنشن للإدارة.<br>
                                                    🔹 4. جميع المعاملات المالية والشراء تتم حصراً عبر التكتات الرسمية فقط.<br>
                                                    🔹 5. يمنع نشر محتوى غير لائق أو سبام داخل الشات العام.<br>
                                                    🔹 6. عند مواجهة أي مشكلة في طلبك، يرجى التوجه لتكت الدعم الفني فوراً.
                                                </div>
                                            </div>
                                            <img src="/static/img/logo.png" class="embed-thumbnail" onerror="this.src='https://cdn.discordapp.com/embed/avatars/0.png'">
                                        </div>
                                        <div class="embed-banner-container" id="preview-rules-banner-container">
                                            <img src="/static/img/ticket_banner.png" class="embed-banner" onerror="this.style.display='none'">
                                        </div>
                                        <div class="embed-footer">
                                            <img src="/static/img/logo.png" class="footer-icon" onerror="this.src='https://cdn.discordapp.com/embed/avatars/0.png'">
                                            <span>FET STORE | نرجو من الجميع الالتزام بالقوانين</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            <!-- Tab 4: Settings -->
            <section class="tab-pane" id="settings-tab">
                <div class="panel-card" style="max-width: 650px; margin: 0 auto;">
                    <h2 class="card-title">⚙️ إعدادات ربط البوت</h2>
                    <div class="form-group">
                        <label>🔑 توكن البوت (Bot Token):</label>
                        <div class="token-wrapper">
                            <input type="password" id="token-input" class="form-input" placeholder="الصق توكن البوت هنا...">
                            <button type="button" id="toggle-token-btn" class="btn-secondary">إظهار</button>
                        </div>
                        <small class="form-hint">تحصل على التوكن من: Discord Developer Portal > Bot > Reset Token</small>
                    </div>
                    <div class="form-group">
                        <label>🛡️ رتبة الإدارة والدعم الفني (Staff Role ID):</label>
                        <select id="staff-role-select" class="form-input">
                            <option value="">-- اختر الرتبة التي تستقبل التكتات --</option>
                        </select>
                        <input type="text" id="staff-role-id-manual" class="form-input mt-2" placeholder="أو اكتب Role ID يدوياً">
                    </div>
                    <div class="form-group">
                        <label>📁 كاتجوري التكتات الفعالة (Active Category):</label>
                        <select id="ticket-category-select" class="form-input">
                            <option value="">-- اختر قسم التكتات الفعالة (تكتات فعالة) --</option>
                        </select>
                        <input type="text" id="category-id-manual" class="form-input mt-2" placeholder="أو اكتب Active Category ID يدوياً">
                    </div>
                    <div class="form-group">
                        <label>📁 كاتجوري التكتات المغلقة (Closed Category):</label>
                        <select id="closed-category-select" class="form-input">
                            <option value="">-- اختر قسم التكتات المغلقة (تكتات مغلقة) --</option>
                        </select>
                        <input type="text" id="closed-category-id-manual" class="form-input mt-2" placeholder="أو اكتب Closed Category ID يدوياً">
                    </div>
                    <button id="btn-save-settings" class="btn-primary">
                        <span>💾 حفظ الإعدادات وإعادة تشغيل البوت</span>
                    </button>
                </div>
            </section>
        </main>
    </div>

    <div id="toast" class="toast hidden">
        <span id="toast-msg">تمت العملية بنجاح!</span>
    </div>

    <script>
let currentConfig = {};
let botData = {};

const botStatusDot = document.querySelector('.status-dot');
const botStatusText = document.getElementById('bot-status-text');
const botProfileCard = document.getElementById('bot-profile-card');
const botUsername = document.getElementById('bot-username');
const botAvatar = document.getElementById('bot-avatar');

document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
        btn.classList.add('active');
        const tabId = btn.dataset.tab;
        document.getElementById(tabId).classList.add('active');
    });
});

const ticketTitleInput = document.getElementById('ticket-title-input');
const ticketDescInput = document.getElementById('ticket-desc-input');
const ticketPlaceholderInput = document.getElementById('ticket-placeholder-input');
const ticketColorInput = document.getElementById('ticket-color-input');
const previewTitle = document.getElementById('preview-title');
const previewDesc = document.getElementById('preview-desc');
const previewSelectPlaceholder = document.getElementById('preview-select-placeholder');
const previewEmbed = document.getElementById('preview-embed');

if(ticketTitleInput) ticketTitleInput.addEventListener('input', (e) => { previewTitle.innerText = e.target.value || 'FET STORE - Support & Ticket System'; });
if(ticketDescInput) ticketDescInput.addEventListener('input', (e) => { previewDesc.innerHTML = (e.target.value || '').replace(/\\n/g, '<br>'); });
if(ticketPlaceholderInput) ticketPlaceholderInput.addEventListener('input', (e) => { previewSelectPlaceholder.innerText = e.target.value || '📂 - اختر نوع الخدمة المطلوبة'; });
if(ticketColorInput) ticketColorInput.addEventListener('input', (e) => { previewEmbed.style.borderLeftColor = e.target.value; });

const updateProductInput = document.getElementById('update-product-input');
const updateDescInput = document.getElementById('update-desc-input');
const previewUpdateTitle = document.getElementById('preview-update-title');
const previewUpdateDesc = document.getElementById('preview-update-desc');

if(updateProductInput) updateProductInput.addEventListener('input', (e) => {
    const val = e.target.value.trim();
    previewUpdateTitle.innerText = val ? `🚀 تم تحديث المنتج: ${val}` : '🚀 تم تحديث المنتج: FET INVENTORY V1.0';
});
if(updateDescInput) updateDescInput.addEventListener('input', (e) => { previewUpdateDesc.innerHTML = (e.target.value || '').replace(/\\n/g, '<br>'); });

const rulesTitleInput = document.getElementById('rules-title-input');
const rulesSubtitleInput = document.getElementById('rules-subtitle-input');
const rulesTextInput = document.getElementById('rules-text-input');
const rulesColorInput = document.getElementById('rules-color-input');
const rulesBannerCheckbox = document.getElementById('rules-banner-checkbox');
const previewRulesTitle = document.getElementById('preview-rules-title');
const previewRulesDesc = document.getElementById('preview-rules-desc');
const previewRulesEmbed = document.getElementById('preview-rules-embed');
const previewRulesBannerContainer = document.getElementById('preview-rules-banner-container');

function updateRulesPreview() {
    if (previewRulesTitle && rulesTitleInput) previewRulesTitle.innerText = rulesTitleInput.value || '📜 قوانين وشروط متجر FET STORE الرسمية';
    if (previewRulesDesc && rulesTextInput) {
        const sub = rulesSubtitleInput ? rulesSubtitleInput.value.trim() : '';
        const rules = (rulesTextInput.value || '').replace(/\\n/g, '<br>');
        previewRulesDesc.innerHTML = sub ? `${sub}<br><br>${rules}` : rules;
    }
    if (previewRulesEmbed && rulesColorInput) previewRulesEmbed.style.borderLeftColor = rulesColorInput.value;
    if (previewRulesBannerContainer && rulesBannerCheckbox) previewRulesBannerContainer.style.display = rulesBannerCheckbox.checked ? 'block' : 'none';
}

if (rulesTitleInput) rulesTitleInput.addEventListener('input', updateRulesPreview);
if (rulesSubtitleInput) rulesSubtitleInput.addEventListener('input', updateRulesPreview);
if (rulesTextInput) rulesTextInput.addEventListener('input', updateRulesPreview);
if (rulesColorInput) rulesColorInput.addEventListener('input', updateRulesPreview);
if (rulesBannerCheckbox) rulesBannerCheckbox.addEventListener('change', updateRulesPreview);

async function loadStatus() {
    try {
        const res = await fetch('/api/status');
        const data = await res.json();
        botData = data;
        currentConfig = data.config || {};

        if (data.online) {
            botStatusDot.className = 'status-dot online';
            botStatusText.innerText = 'البوت متصل بنجاح 🟢';
            if (data.bot_user) {
                botUsername.innerText = data.bot_user;
                if (data.bot_avatar) botAvatar.src = data.bot_avatar;
                botProfileCard.classList.remove('hidden');
            }
            if (data.guilds && data.guilds.length > 0) populateDropdowns(data.guilds);
        } else {
            botStatusDot.className = 'status-dot offline';
            botStatusText.innerText = data.bot_error ? `خطأ: ${data.bot_error}` : 'البوت غير متصل 🔴 (يرجى إدخال التوكن)';
            botProfileCard.classList.add('hidden');
        }

        if (currentConfig.token && document.getElementById('token-input')) {
            document.getElementById('token-input').value = currentConfig.token;
        }
        if (currentConfig.staff_role_id && document.getElementById('staff-role-id-manual')) {
            document.getElementById('staff-role-id-manual').value = currentConfig.staff_role_id;
        }
        if (currentConfig.ticket_category_id && document.getElementById('category-id-manual')) {
            document.getElementById('category-id-manual').value = currentConfig.ticket_category_id;
        }
        if (currentConfig.closed_category_id && document.getElementById('closed-category-id-manual')) {
            document.getElementById('closed-category-id-manual').value = currentConfig.closed_category_id;
        }
    } catch (e) {
        console.error('Error fetching status:', e);
    }
}

function populateDropdowns(guilds) {
    const ticketChannelSelect = document.getElementById('ticket-channel-select');
    const updateChannelSelect = document.getElementById('update-channel-select');
    const rulesChannelSelect = document.getElementById('rules-channel-select');
    const staffRoleSelect = document.getElementById('staff-role-select');
    const categorySelect = document.getElementById('ticket-category-select');
    const closedCategorySelect = document.getElementById('closed-category-select');

    ticketChannelSelect.innerHTML = '<option value="">-- اختر الروم من سيرفرك --</option>';
    updateChannelSelect.innerHTML = '<option value="">-- اختر الروم --</option>';
    if (rulesChannelSelect) rulesChannelSelect.innerHTML = '<option value="">-- اختر الروم --</option>';
    staffRoleSelect.innerHTML = '<option value="">-- اختر الرتبة التي تستقبل التكتات --</option>';
    categorySelect.innerHTML = '<option value="">-- اختر قسم التكتات الفعالة --</option>';
    if (closedCategorySelect) closedCategorySelect.innerHTML = '<option value="">-- اختر قسم التكتات المغلقة --</option>';

    guilds.forEach(g => {
        if (g.channels) {
            g.channels.forEach(ch => {
                ticketChannelSelect.add(new Option(`# ${ch.name} (${g.name})`, ch.id));
                updateChannelSelect.add(new Option(`# ${ch.name} (${g.name})`, ch.id));
                if (rulesChannelSelect) rulesChannelSelect.add(new Option(`# ${ch.name} (${g.name})`, ch.id));
            });
        }
        if (g.roles) {
            g.roles.forEach(r => {
                staffRoleSelect.add(new Option(`@${r.name}`, r.id));
            });
        }
        if (g.categories) {
            g.categories.forEach(cat => {
                categorySelect.add(new Option(`📁 ${cat.name}`, cat.id));
                if (closedCategorySelect) closedCategorySelect.add(new Option(`📁 ${cat.name}`, cat.id));
            });
        }
    });

    if (currentConfig.ticket_channel_id) ticketChannelSelect.value = currentConfig.ticket_channel_id;
    if (currentConfig.updates_channel_id) updateChannelSelect.value = currentConfig.updates_channel_id;
    if (currentConfig.staff_role_id) staffRoleSelect.value = currentConfig.staff_role_id;
    if (currentConfig.ticket_category_id) categorySelect.value = currentConfig.ticket_category_id;
    if (currentConfig.closed_category_id && closedCategorySelect) closedCategorySelect.value = currentConfig.closed_category_id;
}

document.getElementById('btn-send-ticket').addEventListener('click', async () => {
    const channelId = document.getElementById('ticket-channel-select').value;
    if (!channelId) return showToast('⚠️ يرجى اختيار الروم أولاً!');
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
        if (result.status === 'ok') showToast('✅ تم إرسال رسالة التكت بنجاح إلى الديسكورد!');
        else showToast('❌ خطأ: ' + result.message);
    } catch (e) {
        showToast('❌ تعذر الإرسال: ' + e.message);
    }
});

document.getElementById('btn-send-update').addEventListener('click', async () => {
    const channelId = document.getElementById('update-channel-select').value;
    const productName = updateProductInput.value.trim();
    const content = updateDescInput.value.trim();
    const imageUrl = document.getElementById('update-image-input').value.trim();
    if (!channelId || !productName || !content) return showToast('⚠️ يرجى اختيار الروم وكتابة اسم المنتج وتفاصيل التحديث!');
    const payload = { channel_id: channelId, product_name: productName, content: content, image_url: imageUrl };
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
            updateProductInput.value = ''; updateDescInput.value = '';
        } else showToast('❌ خطأ: ' + result.message);
    } catch (e) {
        showToast('❌ تعذر النشر: ' + e.message);
    }
});

const btnSendRules = document.getElementById('btn-send-rules');
if (btnSendRules) {
    btnSendRules.addEventListener('click', async () => {
        const rulesSelect = document.getElementById('rules-channel-select');
        const channelId = rulesSelect ? rulesSelect.value : '';
        const title = rulesTitleInput.value.trim();
        const subtitle = rulesSubtitleInput.value.trim();
        const rulesText = rulesTextInput.value.trim();
        const color = rulesColorInput.value;
        const includeBanner = rulesBannerCheckbox ? rulesBannerCheckbox.checked : true;
        if (!channelId || !rulesText) return showToast('⚠️ يرجى اختيار الروم وكتابة بنود القوانين!');
        const payload = { channel_id: channelId, title: title, subtitle: subtitle, rules_text: rulesText, color: color, include_banner: includeBanner };
        try {
            showToast('⏳ جاري نشر القوانين في الديسكورد...');
            const res = await fetch('/api/rules/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const result = await res.json();
            if (result.status === 'ok') showToast('✅ تم نشر القوانين بنجاح بتصميم مودرن وفخم!');
            else showToast('❌ خطأ: ' + result.message);
        } catch (e) {
            showToast('❌ تعذر النشر: ' + e.message);
        }
    });
}

document.getElementById('btn-save-settings').addEventListener('click', async () => {
    const token = document.getElementById('token-input').value.trim();
    const staffRole = document.getElementById('staff-role-select').value || document.getElementById('staff-role-id-manual').value.trim();
    const category = document.getElementById('ticket-category-select').value || document.getElementById('category-id-manual').value.trim();
    const closedCategory = (document.getElementById('closed-category-select') ? document.getElementById('closed-category-select').value : '') || document.getElementById('closed-category-id-manual').value.trim();
    const payload = { token: token, staff_role_id: staffRole, ticket_category_id: category, closed_category_id: closedCategory };
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

const toggleTokenBtn = document.getElementById('toggle-token-btn');
const tokenInput = document.getElementById('token-input');
if (toggleTokenBtn && tokenInput) {
    toggleTokenBtn.addEventListener('click', () => {
        if (tokenInput.type === 'password') { tokenInput.type = 'text'; toggleTokenBtn.innerText = 'إخفاء'; }
        else { tokenInput.type = 'password'; toggleTokenBtn.innerText = 'إظهار'; }
    });
}

function showToast(msg) {
    const toast = document.getElementById('toast');
    const toastMsg = document.getElementById('toast-msg');
    toastMsg.innerText = msg;
    toast.classList.remove('hidden');
    setTimeout(() => { toast.classList.add('hidden'); }, 3500);
}

document.addEventListener('DOMContentLoaded', () => {
    loadStatus();
    setInterval(loadStatus, 6000);
});
    </script>
</body>
</html>
"""

# [[ Web Dashboard Routes ]] #
@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route("/api/status")
def api_status():
    cfg = load_config()
    is_online = bot.is_ready()
    guilds_data = []
    
    if is_online:
        for g in bot.guilds:
            channels = [{"id": str(c.id), "name": c.name, "type": str(c.type)} for c in g.text_channels]
            roles = [{"id": str(r.id), "name": r.name} for r in g.roles if r.name != "@everyone"]
            categories = [{"id": str(cat.id), "name": cat.name} for cat in g.categories]
            guilds_data.append({
                "id": str(g.id),
                "name": g.name,
                "icon": str(g.icon.url) if g.icon else None,
                "channels": channels,
                "roles": roles,
                "categories": categories
            })
            
    return jsonify({
        "online": is_online,
        "bot_user": str(bot.user) if is_online else None,
        "bot_avatar": str(bot.user.avatar.url) if is_online and bot.user.avatar else None,
        "bot_error": bot_error_msg,
        "config": cfg,
        "guilds": guilds_data
    })

@app.route("/api/config/save", methods=["POST"])
def api_config_save():
    data = request.json or {}
    cfg = load_config()
    old_token = cfg.get("token", "").strip()
    new_token = data.get("token", "").strip()
    
    cfg.update(data)
    save_config(cfg)
    
    if new_token and (new_token != old_token or not bot.is_ready()):
        start_bot_in_background(new_token)
        
    return jsonify({"status": "ok", "message": "Settings saved successfully!"})

@app.route("/api/ticket/send", methods=["POST"])
def api_ticket_send():
    if not bot.is_ready():
        return jsonify({"status": "error", "message": "البوت غير متصل بالديسكورد! يرجى إدخال التوكن في الإعدادات."}), 400
        
    data = request.json or {}
    channel_id = int(data.get("channel_id")) if data.get("channel_id") else None
    if not channel_id:
        return jsonify({"status": "error", "message": "يرجى اختيار الروم المطلوب إرسال التكت فيها."}), 400

    channel = bot.get_channel(channel_id)
    if not channel:
        return jsonify({"status": "error", "message": "الروم غير موجودة أو البوت لا يمتلك صلاحية الوصول لها."}), 404

    cfg = load_config()
    title = data.get("title", cfg.get("ticket_title", "FET STORE - Support & Ticket System"))
    description = data.get("description", cfg.get("ticket_description", ""))
    placeholder = data.get("placeholder", cfg.get("ticket_placeholder", "📂 - اختر نوع الخدمة المطلوبة"))
    color_hex = data.get("color", cfg.get("ticket_color", "#00ff41"))

    async def send_panel():
        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Color.from_str(color_hex)
        )
        
        files = []
        logo_path = os.path.join(ASSETS_DIR, "logo.png")
        banner_path = os.path.join(ASSETS_DIR, "ticket_banner.png")
        
        if os.path.exists(logo_path):
            files.append(discord.File(logo_path, filename="logo.png"))
            embed.set_thumbnail(url="attachment://logo.png")
            embed.set_footer(text="FET STORE | Best Quality Products", icon_url="attachment://logo.png")
            
        if os.path.exists(banner_path):
            files.append(discord.File(banner_path, filename="ticket_banner.png"))
            embed.set_image(url="attachment://ticket_banner.png")

        view = TicketPanelView(placeholder=placeholder)
        if files:
            await channel.send(embed=embed, files=files, view=view)
        else:
            await channel.send(embed=embed, view=view)

    future = asyncio.run_coroutine_threadsafe(send_panel(), bot.loop)
    try:
        future.result(timeout=10)
        return jsonify({"status": "ok", "message": "تم إرسال التكت بنجاح إلى الديسكورد!"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/update/send", methods=["POST"])
def api_update_send():
    if not bot.is_ready():
        return jsonify({"status": "error", "message": "البوت غير متصل بالديسكورد!"}), 400
        
    data = request.json or {}
    channel_id = int(data.get("channel_id")) if data.get("channel_id") else None
    if not channel_id:
        return jsonify({"status": "error", "message": "يرجى اختيار الروم."}), 400

    channel = bot.get_channel(channel_id)
    if not channel:
        return jsonify({"status": "error", "message": "الروم غير موجودة."}), 404

    product_name = data.get("product_name", "المنتج")
    content_text = data.get("content", "")
    image_url = data.get("image_url", "").strip()

    async def send_update():
        embed = discord.Embed(
            title=f"🚀 تم تحديث المنتج: {product_name}",
            description=content_text,
            color=discord.Color.from_str("#00ff41")
        )
        
        files = []
        logo_path = os.path.join(ASSETS_DIR, "logo.png")
        if os.path.exists(logo_path):
            files.append(discord.File(logo_path, filename="logo.png"))
            embed.set_thumbnail(url="attachment://logo.png")
            embed.set_footer(text="FET STORE | New Update Released", icon_url="attachment://logo.png")
        else:
            embed.set_footer(text="FET STORE | New Update Released")

        if image_url:
            embed.set_image(url=image_url)

        if files:
            await channel.send(content="@everyone 📢 تحديث جديد في متجر **FET STORE**", embed=embed, files=files)
        else:
            await channel.send(content="@everyone 📢 تحديث جديد في متجر **FET STORE**", embed=embed)

    future = asyncio.run_coroutine_threadsafe(send_update(), bot.loop)
    try:
        future.result(timeout=10)
        return jsonify({"status": "ok", "message": "تم نشر التحديث بنجاح مع لوقو المتجر!"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/rules/send", methods=["POST"])
def api_rules_send():
    if not bot.is_ready():
        return jsonify({"status": "error", "message": "البوت غير متصل بالديسكورد! يرجى التأكد من ربط التوكن."}), 400
        
    data = request.json or {}
    channel_id = int(data.get("channel_id")) if data.get("channel_id") else None
    if not channel_id:
        return jsonify({"status": "error", "message": "يرجى اختيار الروم المطلوب نشر القوانين فيها."}), 400

    channel = bot.get_channel(channel_id)
    if not channel:
        return jsonify({"status": "error", "message": "الروم غير موجودة أو البوت لا يمتلك صلاحية الوصول لها."}), 404

    title = data.get("title", "📜 قوانين وشروط متجر FET STORE الرسمية")
    subtitle = data.get("subtitle", "")
    rules_text = data.get("rules_text", "")
    color_hex = data.get("color", "#00ff41")
    include_banner = data.get("include_banner", True)

    async def send_rules():
        desc = ""
        if subtitle:
            desc += f"{subtitle}\n\n"
        desc += rules_text

        embed = discord.Embed(
            title=title,
            description=desc,
            color=discord.Color.from_str(color_hex)
        )
        
        files = []
        logo_path = os.path.join(ASSETS_DIR, "logo.png")
        banner_path = os.path.join(ASSETS_DIR, "ticket_banner.png")
        
        if os.path.exists(logo_path):
            files.append(discord.File(logo_path, filename="logo.png"))
            embed.set_thumbnail(url="attachment://logo.png")
            embed.set_author(name="FET STORE | Official Guidelines", icon_url="attachment://logo.png")
            embed.set_footer(text="FET STORE | نرجو من الجميع الالتزام بالقوانين", icon_url="attachment://logo.png")
        else:
            embed.set_author(name="FET STORE | Official Guidelines")
            embed.set_footer(text="FET STORE | نرجو من الجميع الالتزام بالقوانين")

        if include_banner and os.path.exists(banner_path):
            files.append(discord.File(banner_path, filename="ticket_banner.png"))
            embed.set_image(url="attachment://ticket_banner.png")

        if files:
            await channel.send(embed=embed, files=files)
        else:
            await channel.send(embed=embed)

    future = asyncio.run_coroutine_threadsafe(send_rules(), bot.loop)
    try:
        future.result(timeout=10)
        return jsonify({"status": "ok", "message": "تم نشر القوانين بنجاح بتصميم مودرن وفخم!"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

def bot_worker(token):
    global bot_error_msg, bot_thread_active
    bot_thread_active = True
    try:
        asyncio.run(bot.start(token))
    except Exception as e:
        bot_error_msg = str(e)
        logger.error(f"[BOT LOGIN ERROR] {e}")
    finally:
        bot_thread_active = False

def start_bot_in_background(token):
    global bot_thread_active
    if token and not bot_thread_active and not bot.is_ready():
        t = threading.Thread(target=bot_worker, args=(token,), daemon=True)
        t.start()

# Auto-start bot on module load
_init_cfg = load_config()
_init_token = _init_cfg.get("token", "").strip()
if _init_token:
    start_bot_in_background(_init_token)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"[FET DASHBOARD] Server running on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
