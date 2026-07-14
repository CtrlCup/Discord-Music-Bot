import discord
from discord.ext import commands
from utils.db_operations import DatabaseOperations

async def get_roles_for_guild(bot, guild_id: int):
    """Fetch role configuration for a guild from DB"""
    settings = await DatabaseOperations.get_guild_settings(bot.db, guild_id)
    return {
        'user': settings.get('user_role_id'),
        'supporter': settings.get('supporter_role_id'),
        'admin': settings.get('admin_role_id')
    }

async def has_role_or_higher(ctx, role_type: str) -> bool:
    """Helper to check if a user has the required permission level.
    Hierarchy: Admin > Supporter > User.
    If no User role is configured, User commands are open to everyone.
    """
    guilds_to_check = [ctx.guild] if ctx.guild else ctx.bot.guilds
    
    for guild in guilds_to_check:
        member = guild.get_member(ctx.author.id)
        if not member:
            continue
            
        # Check permissions in this specific guild
        if member.guild_permissions.administrator or member.guild_permissions.manage_guild:
            return True

        roles = await get_roles_for_guild(ctx.bot, guild.id)
        user_roles_ids = [r.id for r in member.roles]

        # Check Admin Role
        is_admin = roles['admin'] in user_roles_ids if roles['admin'] else False
        if is_admin:
            return True

        if role_type == 'admin':
            continue

        # Check Supporter Role
        is_supporter = roles['supporter'] in user_roles_ids if roles['supporter'] else False
        if is_supporter:
            return True

        if role_type == 'supporter':
            continue

        # Check User Role
        # If no User role is configured, anyone can run User commands
        if not roles['user'] or roles['user'] in user_roles_ids:
            return True
            
    # Fallback for open User commands in DMs if not member of any guild or not matching roles
    if not ctx.guild and role_type == 'user':
        return True

    return False

# Custom check decorators for commands
def is_admin_check():
    async def predicate(ctx):
        if await has_role_or_higher(ctx, 'admin'):
            return True
        raise commands.MissingPermissions(["Admin-Rolle oder 'Server verwalten'"])
    return commands.check(predicate)

def is_supporter_check():
    async def predicate(ctx):
        if await has_role_or_higher(ctx, 'supporter'):
            return True
        raise commands.MissingPermissions(["Supporter-Rolle oder höher"])
    return commands.check(predicate)

def is_user_check():
    async def predicate(ctx):
        if await has_role_or_higher(ctx, 'user'):
            return True
        raise commands.MissingPermissions(["User-Rolle oder höher"])
    return commands.check(predicate)
