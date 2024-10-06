import os
import io
import discord
from discord.ext import commands
from dotenv import load_dotenv
from generator import Generator
import chess
from chess import Board
from PIL import Image

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

# Disable the default help command
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# Store active invites, games, board states, move history, and player colors
active_invites = {}
games = {}
boards = {}
move_history = {}
colors = {}
draw_offers = {}

@bot.event
async def on_ready():
    print(f"{bot.user.name} is online and ready!")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    await bot.process_commands(message)

# Function to parse square notation to chess coordinates
def parse_square(square: str):
    file = ord(square[0]) - ord('a')  # Convert 'a' to 0, 'b' to 1, etc.
    rank = int(square[1]) - 1  # Convert '1' to 0, '2' to 1, etc.
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
    
    active_invites[ctx.author.id] = member.id
    await ctx.send(f"{member.mention}, you have been invited to play a game by {ctx.author.mention}! Use `!accept` to accept the invitation.")

# Chat command to accept an invitation
@bot.command(name='accept', help='Accept an invitation to play a game.')
async def accept(ctx):
    inviter_id = None
    
    for inviter, invitee in active_invites.items():
        if invitee == ctx.author.id:
            inviter_id = inviter
            break

    if inviter_id is None:
        await ctx.send("You don't have any active invitations.")
        return

    await ctx.send(f"{ctx.author.mention} has accepted the invitation from <@{inviter_id}>! Use `!start` to begin the game.")

    # Store the game state
    boards[(inviter_id, ctx.author.id)] = Board()  # Initialize board
    games[inviter_id] = ctx.author.id  # Store opponent
    games[ctx.author.id] = inviter_id  # Reverse mapping
    move_history[(inviter_id, ctx.author.id)] = []  # Initialize move history

    # Assign colors (White goes first)
    colors[(inviter_id, ctx.author.id)] = (inviter_id, ctx.author.id)  
    del active_invites[inviter_id]  # Remove the invite

# Chat command to start the game
@bot.command(name='start', help='Start the game.')
async def start(ctx):
    if ctx.author.id not in games:
        await ctx.send("You do not have an active game. Please invite someone first.")
        return
    
    opponent_id = games[ctx.author.id]

    # Ensure consistent key order for boards
    board_key = (min(ctx.author.id, opponent_id), max(ctx.author.id, opponent_id))

    # Check if the board has been initialized
    if board_key not in boards:
        await ctx.send("Game board not found. Please check if the game was properly initiated.")
        return

    # Display player colors
    embed = discord.Embed(title="Game Started!", description=f"The game has started between <@{ctx.author.id}> (White) and <@{opponent_id}> (Black)!", color=0x00ff00)
    await ctx.send(embed=embed)

    # Display the initial board
    board_display = await display_board(boards[board_key])
    await ctx.send(file=board_display)

# Chat command to make a move
@bot.command(name="move", aliases=["execute"], help="Executes a move during a chess match")
async def move(ctx, initial: str, final: str):
    author = ctx.message.author

    # Check if the user is in an active game
    if author.id not in games:
        await ctx.send("You are not in an active game.")
        return

    opponent_id = games[author.id]
    # Ensure consistent key order for boards
    board_key = (min(author.id, opponent_id), max(author.id, opponent_id))

    # Check for board existence
    if board_key not in boards:
        await ctx.send("Game board not found. Please make sure you have started the game.")
        return

    board = boards[board_key]
    color = 'white' if author.id == colors[board_key][0] else 'black'

    if (color == 'white' and board.turn == chess.BLACK) or (color == 'black' and board.turn == chess.WHITE):
        await ctx.send("It's not your turn!")
        return

    # Create a move object using chess.Move
    try:
        move = chess.Move.from_uci(f"{initial}{final}")
    except ValueError:
        await ctx.send("Invalid move format. Use !move <initial> <final>.")
        return

    # Check if the move is legal
    if move not in board.legal_moves:
        await ctx.send("Illegal move for the selected piece.")
        return

    # Execute the move
    board.push(move)
    move_history[board_key].append((initial, final))  # Track the move history

    # Check for checkmate
    if board.is_checkmate():
        await ctx.send(f"**Match Finished** - <@{author.id}> wins! Congratulations!")
        del boards[board_key]
        del games[author.id]
        del games[opponent_id]  # Also remove the opponent's entry
        del move_history[board_key]
        del colors[board_key]
    else:
        message = f"Next turn: <@{opponent_id}>"
        await ctx.send(message)

    # Send the updated board
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
    
    # Check if a draw has already been offered
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
    
    # Cleanup
    del boards[(min(ctx.author.id, opponent_id), max(ctx.author.id, opponent_id))]
    del games[ctx.author.id]
    del games[opponent_id]  # Also remove the opponent's entry
    del move_history[(min(ctx.author.id, opponent_id), max(ctx.author.id, opponent_id))]
    del colors[(min(ctx.author.id, opponent_id), max(ctx.author.id, opponent_id))]

# Chat command for help
@bot.command(name='help', help='List all available commands.')
async def help_command(ctx):
    # Send a message in the server chat
    await ctx.send(f"{ctx.author.mention}, check your DMs for more info!")

    # Create an embed for chess commands
    chess_commands_embed = discord.Embed(title="Chess Commands", color=0x00ff00)
    chess_commands = [
        "!invite <user> - Invite a user to play a game. 🤝",
        "!accept - Accept an invitation to play a game. ✔️",
        "!start - Start the game. 🚀",
        "!move <initial> <final> - Make a move during the game. ♟️",
        "!status - Check the current status of the game. 📊",
        "!draw - Offer a draw to your opponent. ✋",
        "!acceptdraw - Accept a draw offer. 🤝",
        "!resign - Resign from the game. 🚪"
    ]
    chess_commands_embed.description = "\n".join(chess_commands)

    # Create an embed for main commands
    main_commands_embed = discord.Embed(title="Main Commands", color=0x00ff00)
    main_commands = [
        "!botstatus - Check the bot's status. 🔍",
        "!invitebot - Invite the bot to your server. 🤖",
        "!botusers - View the number of users. 👥",
        "!botservers - View the number of servers. 🌍",
        "!botuptime - Check the bot's uptime. ⏳"
    ]
    main_commands_embed.description = "\n".join(main_commands)

    # Create buttons
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

    # Send the initial embed with buttons to the user's DMs
    try:
        initial_embed = discord.Embed(title="Choose a Category", description="Click a button below to see commands.", color=0x00ff00)
        await ctx.author.send(embed=initial_embed, view=view)
    except discord.Forbidden:
        await ctx.send("I cannot send you DMs. Please enable DMs to receive the commands.")

# Run the bot
bot.run(TOKEN)
