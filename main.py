import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import asyncio
from urllib.parse import urlencode
import os
import json
import time
import random

# ランダムカラー選択用の関数
def get_random_color():
    """指定された5色からランダムで1色を選択"""
    try:
        colors = [0x808080, 0xFFFFCC, 0xFFFF00, 0xCCCC33, 0xCCFFCC]
        return random.choice(colors)
    except Exception:
        return 0x808080 

BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
CLIENT_ID = os.getenv('DISCORD_CLIENT_ID', '1397029960933445683')
CLIENT_SECRET = os.getenv('DISCORD_CLIENT_SECRET')

# これをいじってね
REDIRECT_URI = 'https://feff8af6-35a2-4af4-93da-320913c2c8fe-00-2vqp07smqvh0j.sisko.replit.dev/'
# ここから下は弄らないでいい
OAUTH_URL_BASE = 'https://discord.com/api/oauth2/authorize'
TOKEN_URL = 'https://discord.com/api/oauth2/token'
USER_URL = 'https://discord.com/api/users/@me'
GUILD_MEMBER_URL = 'https://discord.com/api/guilds/{}/members/{}'

class OAuthBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = False
        intents.guilds = True
        super().__init__(command_prefix='/', intents=intents)

        # データファイルのパス
        self.data_file = 'bot_data.json'

        # 認証済みユーザーを保存（guild_id: [user_ids]）
        self.authenticated_users = {}

        # ユーザーのアクセストークンを保存（user_id: access_token）
        self.user_tokens = {}
    # データをロード
        self.load_data()

    def load_data(self):
        """JSONファイルからデータをロード"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.authenticated_users = data.get('authenticated_users', {})
                    # キーを文字列から整数に変換
                    self.authenticated_users = {int(k): v for k, v in self.authenticated_users.items()}
                    self.user_tokens = data.get('user_tokens', {})
                    print(f'データをロードしました: {len(self.user_tokens)}個のトークン, {len(self.authenticated_users)}個のサーバー')
            else:
                print('データファイルが見つかりません。新規作成します。')
        except Exception as e:
            print(f'データロードエラー: {e}')

    def save_data(self):
        """データをJSONファイルに保存"""
        try:
            data = {
                'authenticated_users': self.authenticated_users,
                'user_tokens': self.user_tokens
            }
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print('データを保存しました')
        except Exception as e:
            print(f'データセーブエラー: {e}')

    async def on_ready(self):
        print(f'{self.user} がログインしました！')

        # スラッシュコマンドを同期
        try:
            synced = await self.tree.sync()
            print(f'{len(synced)}個のスラッシュコマンドを同期しました')
        except Exception as e:
            print(f'スラッシュコマンドの同期エラー: {e}')

        # Webサーバーを開始
        await self.start_web_server()

    async def start_web_server(self):
        from aiohttp import web

        app = web.Application()
        app.router.add_get('/', self.handle_oauth_callback)
        app.router.add_static('/attached_assets/', path='attached_assets', name='static')

        runner = web.AppRunner(app)
        await runner.setup()

        port = int(os.getenv('PORT', 10000))
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        print(f'Webサーバーが http://0.0.0.0:{port} で開始されました')

    async def handle_oauth_callback(self, request):
        from aiohttp import web

        code = request.query.get('code')
        error = request.query.get('error')

        if error:
            return web.Response(text=f'認証エラー: {error}', status=400)

        if not code:
            return web.Response(text='認証コードが見つかりません', status=400)

        try:
            # アクセストークンを取得
            token_data = await self.get_access_token(code)
            access_token = token_data['access_token']

            # ユーザー情報を取得
            user_data = await self.get_user_info(access_token)
            user_id = user_data['id']
            username = user_data['username']

            # アクセストークンを保存
            self.user_tokens[user_id] = access_token

            # stateからサーバーIDとロールIDを取得
            state = request.query.get('state', '')
            guild_id = None
            role_id = None

            if state.startswith('discord_oauth_'):
                parts = state.replace('discord_oauth_', '').split('_')
                if len(parts) >= 2:
                    guild_id = int(parts[0])
                    role_id = int(parts[1])

            if not guild_id or not role_id:
                return web.Response(text='サーバー情報またはロール情報が見つかりません', status=400)

            # サーバーにメンバーを追加
            success = await self.add_member_to_guild(access_token, user_id, guild_id)

            if success:
                # メンバー確認
                guild = self.get_guild(guild_id)
                member_found = False

                if guild:
                    for attempt in range(5):
                        try:
                            member = await guild.fetch_member(int(user_id))
                            member_found = True
                            break
                        except discord.NotFound:
                            if attempt < 4:
                                await asyncio.sleep(2)
                        except Exception as e:
                            if attempt < 4:
                                await asyncio.sleep(2)

                if member_found:
                    # ロール付与
                    role_assigned = await self.assign_role(user_id, guild_id, role_id)

                    # 認証済みユーザーとして記録
                    if guild_id not in self.authenticated_users:
                        self.authenticated_users[guild_id] = []
                    if user_id not in self.authenticated_users[guild_id]:
                        self.authenticated_users[guild_id].append(user_id)
                    self.authenticated_users[guild_id].append(user_id)
                    self.save_data()
                    html = '''
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <title>認証完了</title>
                        <meta charset="UTF-8">
                        <style>
                            body {
                                font-family: 'Hiragino Sans', 'Hiragino Kaku Gothic ProN', 'Noto Sans JP', sans-serif;
                                text-align: center;
                                margin: 0;
                                padding: 0;
                                background-image: url('/attached_assets/image_1753631286001.png');
                                background-size: cover;
                                background-position: center;
                                background-repeat: no-repeat;
                                background-attachment: fixed;
                                min-height: 100vh;
                                display: flex;
                                align-items: center;
                                justify-content: center;
                            }
                            .container {
                                max-width: 600px;
                                background: rgba(40, 40, 40, 0.6);
                                padding: 60px 40px;
                                border-radius: 10px;
                                box-shadow: 0 2px 20px rgba(0,0,0,0.3);
                                backdrop-filter: blur(10px);
                            }
                            .check-icon {
                                width: 80px;
                                height: 80px;
                                background-color: #28a745;
                                border-radius: 50%;
                                display: inline-flex;
                                align-items: center;
                                justify-content: center;
                                margin-bottom: 30px;
                            }
                            .check-icon::after {
                                content: "✓";
                                color: white;
                                font-size: 40px;
                                font-weight: bold;
                            }
                            .title {
                                font-size: 48px;
                                font-weight: bold;
                                color: #ffffff;
                                margin-bottom: 40px;
                            }
                            .message {
                                font-size: 24px;
                                color: #ffffff;
                                line-height: 1.4;
                            }
                        </style>
                    </head>
                    <body>
                        <div class="container">
                            <div class="check-icon"></div>
                            <div class="title">認証完了</div>
                            <div class="message">・認証へのご協力ありがとうございます</div>
                        </div>
                    </body>
                    </html>
                    '''
                    return web.Response(text=html, content_type='text/html', status=200)

            return web.Response(text='サーバー参加に失敗', status=400)

        except Exception as e:
            return web.Response(text=f'処理中にエラーが発生しました: {e}', status=500)

    async def get_access_token(self, code):
        data = {
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': REDIRECT_URI
        }

        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(TOKEN_URL, data=data) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    raise Exception(f'トークン取得失敗: {response.status}')

    async def get_user_info(self, access_token):
        headers = {'Authorization': f'Bearer {access_token}'}

        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(USER_URL, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    raise Exception(f'ユーザー情報取得失敗: {response.status}')

    async def add_member_to_guild(self, access_token, user_id, guild_id):
        url = GUILD_MEMBER_URL.format(guild_id, user_id)
        headers = {
            'Authorization': f'Bot {BOT_TOKEN}',
            'Content-Type': 'application/json'
        }
        data = {'access_token': access_token}

        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.put(url, headers=headers, json=data) as response:
                return response.status in [200, 201, 204]

    async def assign_role(self, user_id, guild_id, role_id):
        url = f"https://discord.com/api/guilds/{guild_id}/members/{user_id}/roles/{role_id}"
        headers = {
            'Authorization': f'Bot {BOT_TOKEN}',
            'Content-Type': 'application/json'
        }

        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.put(url, headers=headers) as response:
                return response.status == 204

    async def close(self):
        """ボット終了時のクリーンアップ"""
        await super().close()

# ボットインスタンス
bot = OAuthBot()

class AuthLinkView(discord.ui.View):
    def __init__(self, guild, role):
        super().__init__(timeout=None)
        self.guild = guild
        self.role = role

        params = {
            'client_id': CLIENT_ID,
            'redirect_uri': REDIRECT_URI,
            'response_type': 'code',
            'scope': 'identify guilds.join',
            'state': f'discord_oauth_{guild.id}_{role.id}'
        }
        oauth_link = f"{OAUTH_URL_BASE}?{urlencode(params)}"

        self.add_item(discord.ui.Button(
            label='にんしょう！',
            style=discord.ButtonStyle.link,
            url=oauth_link
        ))

# 認証パネル作成コマンド
@bot.tree.command(name='role', description='認証メッセージを送信します')
@app_commands.describe(role='付与したいロールを選択してね', channel='このパネルを送るチャンネルを選択（省略した場合は現在のチャンネル）')
@app_commands.default_permissions(administrator=True)
async def role_slash(interaction: discord.Interaction, role: discord.Role, channel: discord.TextChannel = None):
    target_channel = channel or interaction.channel
    view = AuthLinkView(interaction.guild, role)

    try:
        color = get_random_color()
    except Exception:
        color = 0x808080

    embed = discord.Embed(
        title="こんにちは！",
        description="ボタンを押してにんしょうしてね！",
        color=color
    )

    await target_channel.send(embed=embed, view=view)
    await interaction.response.send_message(f"認証メッセージを {target_channel.mention} に送信しました", ephemeral=True)

# 認証済みユーザーをサーバーに追加するコマンド
@bot.tree.command(name='call', description='認証済みユーザーをこのサーバーに追加します')
@app_commands.default_permissions(administrator=True)
async def backup_slash(interaction: discord.Interaction, message: str = None):
    target_guild_id = interaction.guild.id

    # 全サーバーの認証済みユーザーを取得
    all_authenticated_users = []
    for guild_id, users in bot.authenticated_users.items():
        all_authenticated_users.extend(users)

    # 重複を除去
    all_authenticated_users = list(set(all_authenticated_users))

    if not all_authenticated_users:
        await interaction.response.send_message("認証済みユーザーいなくね？", ephemeral=True)
        return

    await interaction.response.send_message("認証済みユーザーをサーバーに追加中", ephemeral=True)

    added_users = []
    already_in_server = []
    failed_users = []

    for user_id in all_authenticated_users:
        try:
            # 既にサーバーにいるかチェック
            member = interaction.guild.get_member(int(user_id))
            if member:
                already_in_server.append(member.display_name)
                continue

            # ユーザーのアクセストークンがあるかチェック
            if user_id not in bot.user_tokens:
                failed_users.append(f"ユーザーID: {user_id} (トークンなし)")
                continue

            access_token = bot.user_tokens[user_id]

            # サーバーに追加
            success = await bot.add_member_to_guild(access_token, user_id, target_guild_id)

            if success:
                # 少し待ってからメンバー確認
                await asyncio.sleep(1)
                try:
                    member = await interaction.guild.fetch_member(int(user_id))
                    added_users.append(member.display_name)

                    # このサーバーの認証済みユーザーリストに追加
                    if target_guild_id not in bot.authenticated_users:
                        bot.authenticated_users[target_guild_id] = []
                    if user_id not in bot.authenticated_users[target_guild_id]:
                        bot.authenticated_users[target_guild_id].append(user_id)

                except discord.NotFound:
                    failed_users.append(f"ユーザーID: {user_id} (追加後見つからず)")
            else:
                failed_users.append(f"ユーザーID: {user_id} (追加失敗)")

        except Exception as e:
            failed_users.append(f"ユーザーID: {user_id} (エラー: {str(e)[:50]})")

    # 結果を報告
    add = len(added_users)
    in_tintin = len(already_in_server)
    failed = len(failed_users)

    result_message = f"**追加完了:** {add}人追加、{in_tintin}人既存、{failed}人失敗"

    if message:
        result_message += f"\n\n**メッセージ:** {message}"
    bot.save_data()
    await interaction.followup.send(result_message)

async def run_bot():
    """ボットを実行する非同期関数"""
    try:
        await bot.start(BOT_TOKEN)
    except KeyboardInterrupt:
        print("ボットが手動で停止されました")
    except Exception as e:
        print(f"ボットの起動に失敗しました: {e}")
    finally:
        if not bot.is_closed():
            await bot.close()

def main():
    if not BOT_TOKEN:
        print("DISCORD_BOT_TOKEN環境変数が設定されていません")
        print("Secrets ツールでトークンを設定してください")
        return

    if not CLIENT_ID or not CLIENT_SECRET:
        print("DISCORD_CLIENT_IDまたはDISCORD_CLIENT_SECRET環境変数が設定されていません")
        print("Secrets ツールでクライアント情報を設定してください")
        return

    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        print("ボットが手動で停止されました")
    except Exception as e:
        print(f"予期しないエラー: {e}")

if __name__ == "__main__":
    main()
