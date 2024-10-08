import os
import io
import discord
from discord.ext import commands
from dotenv import load_dotenv
from generator import Generator
import chess
from chess import Board
from PIL import Image
import json
import time
import random

# Load environment variables from .env file
load_dotenv()
TOKEN = os.getenv("TOKEN")

if TOKEN is None:
    print("Error: Token not found. Please check your .env file.")
    exit()

# Set up intents and bot
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# Store active invites, games, board states, move history, player colors, and stats
active_invites = {}
games = {}
boards = {}
move_history = {}
colors = {}
draw_offers = {}
user_stats = {}

# Load user statistics from a JSON file
def load_user_stats():
    global user_stats
    if os.path.exists('user_stats.json'):
        with open('user_stats.json', 'r') as f:
            user_stats = json.load(f)

# Save user statistics to a JSON file
def save_user_stats():
    with open('user_stats.json', 'w') as f:
        json.dump(user_stats, f)

# Initialize user statistics
def initialize_user(user_id):
    if str(user_id) not in user_stats:
        user_stats[str(user_id)] = {"wins": 0, "losses": 0, "draws": 0, "total_games": 0, "rating": 50}

@bot.event
async def on_ready():
    print(f"{bot.user.name} is online and ready!")
    load_user_stats()

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    await bot.process_commands(message)

# Function to parse square notation to chess coordinates
def parse_square(square: str):
    file = ord(square[0]) - ord('a')
    rank = int(square[1]) - 1
    return (file, rank)

# Function to display the board
async def display_board(board: Board):
    with io.BytesIO() as binary:
        image = Generator.generate(board)
        image = image.resize((500, 500), Image.LANCZOS)
        image.save(binary, "PNG")
        binary.seek(0)
        return discord.File(fp=binary, filename="board.png")

# Chat command to invite a user
@bot.command(name='invite', help='Invite a user to play a game.')
async def invite(ctx, member: discord.Member):
    if member == ctx.author:
        await ctx.send("You cannot invite yourself!")
        return
    
    if member.id in games:
        await ctx.send(f"{member.mention} is already in an active game and cannot be invited.")
        return

    active_invites[ctx.author.id] = member.id
    await ctx.send(f"{member.mention}, you have been invited to play a game by {ctx.author.mention}! Use `!accept` to accept the invitation.")

# Chat command to accept an invitation
@bot.command(name='accept', help='Accept an invitation to play a game.')
async def accept(ctx):
    if ctx.author.id in games:
        await ctx.send("You are already in an active game and cannot accept another invitation.")
        return

    inviter_id = None
    
    for inviter, invitee in active_invites.items():
        if invitee == ctx.author.id:
            inviter_id = inviter
            break

    if inviter_id is None:
        await ctx.send("You don't have any active invitations.")
        return

    await ctx.send(f"{ctx.author.mention} has accepted the invitation from <@{inviter_id}>! Use `!start` to begin the game.")

    boards[(inviter_id, ctx.author.id)] = Board()
    games[inviter_id] = ctx.author.id
    games[ctx.author.id] = inviter_id
    move_history[(inviter_id, ctx.author.id)] = []

    colors[(inviter_id, ctx.author.id)] = (inviter_id, ctx.author.id)
    del active_invites[inviter_id]

    initialize_user(inviter_id)
    initialize_user(ctx.author.id)

# Chat command to start the game
@bot.command(name='start', help='Start the game.')
async def start(ctx):
    if ctx.author.id not in games:
        await ctx.send("You do not have an active game. Please invite someone first.")
        return
    
    opponent_id = games[ctx.author.id]
    board_key = (min(ctx.author.id, opponent_id), max(ctx.author.id, opponent_id))

    if board_key not in boards:
        await ctx.send("Game board not found. Please check if the game was properly initiated.")
        return

    embed = discord.Embed(title="Game Started!", description=f"The game has started between <@{ctx.author.id}> (White) and <@{opponent_id}> (Black)!", color=0x00ff00)
    await ctx.send(embed=embed)

    board_display = await display_board(boards[board_key])
    await ctx.send(file=board_display)

# Chat command to make a move
@bot.command(name="move", aliases=["execute"], help="Executes a move during a chess match")
async def move(ctx, initial: str, final: str):
    author = ctx.message.author

    if author.id not in games:
        await ctx.send("You are not in an active game.")
        return

    opponent_id = games[author.id]
    board_key = (min(author.id, opponent_id), max(author.id, opponent_id))

    if board_key not in boards:
        await ctx.send("Game board not found. Please make sure you have started the game.")
        return

    board = boards[board_key]
    color = 'white' if author.id == colors[board_key][0] else 'black'

    if (color == 'white' and board.turn == chess.BLACK) or (color == 'black' and board.turn == chess.WHITE):
        await ctx.send("It's not your turn!")
        return

    try:
        move = chess.Move.from_uci(f"{initial}{final}")
    except ValueError:
        await ctx.send("Invalid move format. Use !move <initial> <final>.")
        return

    if move not in board.legal_moves:
        await ctx.send("Illegal move for the selected piece.")
        return

    board.push(move)
    move_history[board_key].append((initial, final))

    user_stats[str(author.id)]["total_games"] += 1
    user_stats[str(opponent_id)]["total_games"] += 1

    if board.is_checkmate():
        await ctx.send(f"**Match Finished** - <@{author.id}> wins! Congratulations!")
        user_stats[str(author.id)]["wins"] += 1
        user_stats[str(opponent_id)]["losses"] += 1
        user_stats[str(author.id)]["rating"] += 10
        user_stats[str(opponent_id)]["rating"] -= 5
        save_user_stats()
        del boards[board_key]
        del games[author.id]
        del games[opponent_id]
        del move_history[board_key]
        del colors[board_key]
    else:
        message = f"Next turn: <@{opponent_id}>"
        await ctx.send(message)

    board_display = await display_board(board)
    await ctx.send(file=board_display)

# Chat command to check game status
@bot.command(name='status', help='Check the current status of the game.')
async def status(ctx):
    if ctx.author.id not in games:
        await ctx.send("You do not have an active game.")
        return
    
    opponent_id = games[ctx.author.id]
    game_board = boards[(min(ctx.author.id, opponent_id), max(ctx.author.id, opponent_id))]
    move_history_str = "\n".join([f"{i + 1}. {move[0]} to {move[1]}" for i, move in enumerate(move_history[(min(ctx.author.id, opponent_id), max(ctx.author.id, opponent_id))])])
    
    embed = discord.Embed(title="Game Status", description=f"Current Board:\n\nMove History:\n{move_history_str or 'No moves made yet.'}", color=0x00ff00)
    await ctx.send(embed=embed)

# Chat command to offer a draw
@bot.command(name='draw', help='Offer a draw to your opponent.')
async def draw(ctx):
    if ctx.author.id not in games:
        await ctx.send("You are not in an active game.")
        return

    opponent_id = games[ctx.author.id]
    
    if (ctx.author.id, opponent_id) in draw_offers:
        await ctx.send("You have already offered a draw.")
        return

    draw_offers[(ctx.author.id, opponent_id)] = True
    await ctx.send(f"{ctx.author.mention} has offered a draw to <@{opponent_id}>. Use `!acceptdraw` to accept.")

# Chat command to accept a draw
@bot.command(name='acceptdraw', help='Accept a draw offer.')
async def accept_draw(ctx):
    if ctx.author.id not in games:
        await ctx.send("You are not in an active game.")
        return
    
    opponent_id = games[ctx.author.id]
    
    if (opponent_id, ctx.author.id) not in draw_offers:
        await ctx.send("No draw offer has been made to you.")
        return

    await ctx.send(f"**Match Finished** - The game is a draw! Thanks for playing!")
    user_stats[str(ctx.author.id)]["draws"] += 1
    user_stats[str(opponent_id)]["draws"] += 1
    user_stats[str(ctx.author.id)]["rating"] += 5
    user_stats[str(opponent_id)]["rating"] += 5
    save_user_stats()
    del boards[(min(ctx.author.id, opponent_id), max(ctx.author.id, opponent_id))]
    del games[ctx.author.id]
    del games[opponent_id]
    del move_history[(min(ctx.author.id, opponent_id), max(ctx.author.id, opponent_id))]
    del colors[(min(ctx.author.id, opponent_id), max(ctx.author.id, opponent_id))]
    del draw_offers[(opponent_id, ctx.author.id)]

# Chat command to forfeit the game
@bot.command(name='resign', help='Resign the game.')
async def forfeit(ctx):
    if ctx.author.id not in games:
        await ctx.send("You do not have an active game.")
        return
    
    opponent_id = games[ctx.author.id]
    await ctx.send(f"{ctx.author.mention} has resigned from the game. <@{opponent_id}> wins!")
    
    user_stats[str(opponent_id)]["wins"] += 1
    user_stats[str(ctx.author.id)]["losses"] += 1
    user_stats[str(opponent_id)]["rating"] += 10
    user_stats[str(ctx.author.id)]["rating"] -= 5
    save_user_stats()

    del boards[(min(ctx.author.id, opponent_id), max(ctx.author.id, opponent_id))]
    del games[ctx.author.id]
    del games[opponent_id]
    del move_history[(min(ctx.author.id, opponent_id), max(ctx.author.id, opponent_id))]
    del colors[(min(ctx.author.id, opponent_id), max(ctx.author.id, opponent_id))]

# Chat command to view user statistics
@bot.command(name='stats', help='View your or another user\'s chess statistics. Usage: !stats <user>')
async def stats(ctx, member: discord.Member = None):
    if member is None:
        member = ctx.author  # Default to the command invoker

    initialize_user(member.id)
    user_stat = user_stats[str(member.id)]
    
    embed = discord.Embed(title=f"{member.name}'s Chess Statistics", color=0x00ff00)
    embed.set_thumbnail(url=member.avatar.url)
    embed.add_field(name="Games Played", value=user_stat["total_games"], inline=False)
    embed.add_field(name="Wins", value=user_stat["wins"], inline=True)
    embed.add_field(name="Losses", value=user_stat["losses"], inline=True)
    embed.add_field(name="Draws", value=user_stat["draws"], inline=True)
    embed.add_field(name="Rating", value=user_stat["rating"], inline=True)
    
    await ctx.send(embed=embed)

# Chat command for help
@bot.command(name='help', help='List all available commands.')
async def help_command(ctx):
    await ctx.send(f"{ctx.author.mention}, check your DMs for more info!")

    chess_commands_embed = discord.Embed(title="Chess Commands", color=0x00ff00)
    chess_commands = [
        "!invite <user> - Invite a user to play a game. 🤝",
        "!accept - Accept an invitation to play a game. ✔️",
        "!start - Start the game. 🚀",
        "!move <initial> <final> - Make a move during the game. ♟️",
        "!status - Check the current status of the game. 📊",
        "!draw - Offer a draw to your opponent. ✋",
        "!acceptdraw - Accept a draw offer. 🤝",
        "!resign - Resign from the game. 🚪",
        "!stats - View your chess statistics. 📊"
    ]
    chess_commands_embed.description = "\n".join(chess_commands)

    main_commands_embed = discord.Embed(title="Main Commands", color=0x00ff00)
    main_commands = [
        "!botstatus - Check the bot's status. 🔍",
        "!invitebot - Invite the bot to your server. 🤖",
        "!botusers - View the number of users. 👥",
        "!botservers - View the number of servers. 🌍",
        "!botuptime - Check the bot's uptime. ⏳",
        "!serverinfo - Get information about the server.🪙",
        "!coinflip - Flip a coin. 🪙",
        "!joke - Get a random joke. 😂"
    ]
    main_commands_embed.description = "\n".join(main_commands)

    button_chess = discord.ui.Button(label="Chess Commands", style=discord.ButtonStyle.primary)
    button_main = discord.ui.Button(label="Main Commands", style=discord.ButtonStyle.primary)

    async def chess_callback(interaction):
        await interaction.response.edit_message(embed=chess_commands_embed)

    async def main_callback(interaction):
        await interaction.response.edit_message(embed=main_commands_embed)

    button_chess.callback = chess_callback
    button_main.callback = main_callback

    view = discord.ui.View()
    view.add_item(button_chess)
    view.add_item(button_main)

    try:
        initial_embed = discord.Embed(title="Choose a Category", description="Click a button below to see commands.", color=0x00ff00)
        await ctx.author.send(embed=initial_embed, view=view)
    except discord.Forbidden:
        await ctx.send("I cannot send you DMs. Please enable DMs to receive the commands.")

# Chat command to check the bot's status
@bot.command(name='botstatus', help='Check the bot\'s status.')
async def bot_status(ctx):
    embed = discord.Embed(title="Bot Status", color=0x00ff00)
    embed.add_field(name="Bot Name", value=bot.user.name, inline=True)
    embed.add_field(name="Bot ID", value=bot.user.id, inline=True)
    embed.add_field(name="Servers", value=len(bot.guilds), inline=True)
    embed.add_field(name="Users", value=len(set(bot.get_all_members())), inline=True)
    embed.add_field(name="Uptime", value=f"{time.time() - bot.start_time:.2f} seconds", inline=True)
    await ctx.send(embed=embed)

# Chat command to invite the bot to a server
@bot.command(name='invitebot', help='Invite the bot to your server.')
async def invite_bot(ctx):
    invite_link = discord.utils.oauth_url(bot.user.id, permissions=discord.Permissions(permissions=8))  # Adjust permissions as necessary
    await ctx.send(f"Click [here]({invite_link}) to invite the bot to your server!")

# Chat command to get the number of users
@bot.command(name='botusers', help='View the number of users.')
async def bot_users(ctx):
    user_count = len(set(bot.get_all_members()))
    await ctx.send(f"The bot is currently in {user_count} users across all servers.")

# Chat command to get the number of servers
@bot.command(name='botservers', help='View the number of servers.')
async def bot_servers(ctx):
    server_count = len(bot.guilds)
    await ctx.send(f"The bot is currently in {server_count} servers.")

# Chat command to get information about the server
@bot.command(name='serverinfo', help='Get information about the server.')
async def server_info(ctx):
    if ctx.guild is None:
        await ctx.send("This command can only be used in a server.")
        return

    guild = ctx.guild
    embed = discord.Embed(title=f"Server Information", color=0x00ff00)
    embed.add_field(name="Server Name", value=guild.name, inline=True)
    embed.add_field(name="Server ID", value=guild.id, inline=True)
    embed.add_field(name="Member Count", value=guild.member_count, inline=True)
    embed.add_field(name="Creation Date", value=guild.created_at.strftime("%Y-%m-%d %H:%M:%S"), inline=True)

    if guild.icon:
        embed.set_thumbnail(url=str(guild.icon))

    await ctx.send(embed=embed)

# Chat command to check the bot's uptime
@bot.command(name='botuptime', help='Check the bot\'s uptime.')
async def bot_uptime(ctx):
    uptime = time.time() - bot.start_time
    await ctx.send(f"The bot has been running for {uptime:.2f} seconds.")

# Fun command to flip a coin
@bot.command(name='coinflip', help='Flip a coin.')
async def coinflip(ctx):
    result = random.choice(['Heads', 'Tails'])
    await ctx.send(f"The coin landed on: **{result}**")

# Fun command to tell a joke
@bot.command(name='joke', help='Get a random joke.')
async def joke(ctx):
    jokes = [
        "Why did the scarecrow win an award? Because he was outstanding in his field!",
        "I told my computer I needed a break, and now it won't stop sending me Kit-Kat ads.",
        "Why don't skeletons fight each other? They don't have the guts."
    ]
    await ctx.send(random.choice(jokes))

# Run the bot
bot.start_time = time.time()
bot.run(TOKEN)
