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
    if not ctx.guild:
        # In DMs, allow User-level commands but reject Supporter/Admin commands
        return role_type == 'user'

    # Discord Administrators or users with Manage Guild are always Admins
    if ctx.author.guild_permissions.administrator or ctx.author.guild_permissions.manage_guild:
        return True

    roles = await get_roles_for_guild(ctx.bot, ctx.guild.id)
    user_roles_ids = [r.id for r in ctx.author.roles]

    # Check Admin Role
    is_admin = roles['admin'] in user_roles_ids if roles['admin'] else False
    if is_admin:
        return True

    if role_type == 'admin':
        return False

    # Check Supporter Role
    is_supporter = roles['supporter'] in user_roles_ids if roles['supporter'] else False
    if is_supporter:
        return True

    if role_type == 'supporter':
        return False

    # Check User Role
    # If no User role is configured, anyone can run User commands
    if not roles['user']:
        return True

    return roles['user'] in user_roles_ids

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
