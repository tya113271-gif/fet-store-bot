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

from flask import Flask, render_template, request, jsonify
import discord
from discord.ext import commands

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "data", "config.json")
ASSETS_DIR = os.path.join(BASE_DIR, "static", "img")

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)

# [[ Flask Web Dashboard ]] #
app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["SECRET_KEY"] = "fet_store_secret_2026"

# [[ Discord Bot Setup ]] #
intents = discord.Intents.default()
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot_loop = None
bot_error_msg = None

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
    # Check if user has any role containing staff/admin/owner/support
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
            
    # Auto-detection by keyword
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
        
        # Find Ticket Owner from topic ID: (\d+)
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
            # Fallback
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

        # 1. Check if user is Staff/Admin - ONLY Staff can close tickets!
        if not is_user_staff(user, guild, staff_role_id):
            await interaction.response.send_message("❌ عذراً، إغلاق التذكرة متاح فقط لطاقم الإدارة والدعم الفني.", ephemeral=True)
            return

        await interaction.response.send_message(f"🔒 تم إغلاق التذكرة بواسطة {user.mention}. تم سحب صلاحية المشاهدة من العميل ونقل التذكرة إلى قسم التكتات المغلقة (للإدارة فقط).", ephemeral=False)
        
        staff_role = guild.get_role(int(staff_role_id)) if staff_role_id else None

        # 2. Move to Closed Category
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

        # 3. Lock @everyone on this channel
        try:
            await channel.set_permissions(guild.default_role, overwrite=discord.PermissionOverwrite(
                view_channel=False,
                read_messages=False,
                send_messages=False,
                read_message_history=False
            ))
        except Exception as e:
            logger.error(f"Error locking default role: {e}")

        # 4. Explicitly deny all non-staff members in overwrites
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

        # 5. Explicitly deny all non-staff members currently in channel.members
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

        # 6. Extract ticket owner by ID from topic and deny
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

        # 7. Ensure Staff Role retains full view permissions
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

        # 8. Send closed action panel
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
        
        # Find Active Category (تكتات فعالة)
        active_cat = get_target_category(guild, "ticket_category_id", ["فعال", "active", "تكتات فعالة", "open"])
        
        # Overwrites
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

# [[ Web Dashboard Routes ]] #
@app.route("/")
def index():
    return render_template("index.html")

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
    
    if new_token and new_token != old_token:
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

def bot_worker(token):
    global bot_loop, bot_error_msg
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    bot_loop = loop
    try:
        loop.run_until_complete(bot.start(token))
    except Exception as e:
        bot_error_msg = str(e)
        logger.error(f"[BOT LOGIN ERROR] {e}")

def start_bot_in_background(token):
    if token:
        threading.Thread(target=bot_worker, args=(token,), daemon=True).start()

if __name__ == "__main__":
    cfg = load_config()
    token = cfg.get("token", "").strip()
    if token:
        start_bot_in_background(token)
        
    port = int(os.environ.get("PORT", 5000))
    print(f"[FET DASHBOARD] Server running on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
