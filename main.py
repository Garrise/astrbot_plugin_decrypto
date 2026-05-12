from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult, MessageChain
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.all import AstrBotConfig, Image, Plain, At
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import AiocqhttpMessageEvent

import random, math, asyncio, time
from pathlib import Path
from collections import defaultdict

class DecryptoSession():
    def __init__(self, decrypt_timeout: int = 300, encrypt_timeout: int = 1800):            
        with open(Path(__file__).parent / "keywords.txt", "r", encoding="utf-8") as f:
            self.keywords = f.read().split(",")
        self.history_keywords = []
        self.history_passwords = []
        self.black_teams = []
        self.white_teams = []
        self._generate_keyword()

        self.black_cipher = []
        self.white_cipher = []
        self.black_history_ciphers = []
        self.white_history_ciphers = []

        self.password = "" # 当前回合的密码
        self.enemy_password = "" # 当前非加密方猜测的密码
        self.ally_password = "" # 当前加密方猜测的密码

        self.encrypter = ""

        self.black_intercepts = 0
        self.white_intercepts = 0
        self.white_errors = 0
        self.black_errors = 0

        self.turn = 0 # 最大回合数16，双方各8，奇数为黑队回合，偶数为白队回合
        self.phase = 0 # 回合内阶段， 0为加密阶段，1为敌方截码阶段，2为敌方译码阶段
        self.max_turns = 16

        # 状态标识
        self.start_flag = False
        self.custom_keywords = False
        self.custom_keywords_set = False
        self.keywords_sent = False
        self.is_game_set = False
        self.black_confirmed = False
        self.white_confirmed = False
        self.game_set_reply = ""

        #计时
        self.black_timeout = encrypt_timeout
        self.white_timeout = encrypt_timeout
        self.encrypt_start_time: int = 0

    def shuffle_teams(self):
        random.shuffle(self.black_teams)
        random.shuffle(self.white_teams)

    def game_start(self):
        self.shuffle_teams()
        start_reply = "队伍结成！开始分配关键字！"
        start_reply += "\n\n【黑队】"
        for index, member in enumerate(self.black_teams, start = 1):
            start_reply += f"\n{index}. {member[1]}"
        start_reply += "\n\n【白队】"
        for index, member in enumerate(self.white_teams, start = 1):
            start_reply += f"\n{index}. {member[1]}"
        start_reply += "\n\n请各队成员确认关键字！"
        return start_reply


    def turn_change(self):
        self.turn += 1
        turn = math.ceil(self.turn / 2)
        player_seq = turn - 1
        black_index = player_seq % len(self.black_teams)
        white_index = player_seq % len(self.white_teams)
        reply = []
        reply.append(Plain(f"第{turn}回合，"))
        
        if self.turn % 2 == 1:
            self.encrypter = self.black_teams[black_index][0]
            reply.append(Plain("黑方加密员："))
            reply.append(At(qq=self.encrypter))
        else:
            self.encrypter = self.white_teams[white_index][0]
            reply.append(Plain("白方加密员："))
            reply.append(At(qq=self.encrypter))
        self.phase = 0

        # 私聊密码
        self._generate_password()

        return reply


    def encrypt(self, cipher1: str, cipher2: str, cipher3: str):
        ciphers = [cipher1, cipher2, cipher3]
        cipher_record = [""] * 4
        reply = []
        for i, cipher in zip(self.password, ciphers):
            cipher_record[int(i) - 1] = cipher
        if self.turn % 2 == 1:
            self.black_cipher = cipher_record
            decrypt_side = "白"
        else:
            self.white_cipher = cipher_record
            decrypt_side = "黑"
        if self.turn / 2 <= 1: # 第一回合不提示密码
            self.phase = 2
            if decrypt_side == "黑":
                decrypt_side = "白"
            else: 
                decrypt_side = "黑"
            reply.append(Plain(f"加密完成！首回合无拦截阶段\n请{decrypt_side}队进行破解！"))
        else:
            self.phase = 1
            reply.append(Plain(f"加密完成！\n请{decrypt_side}队进行破解！"))
        if decrypt_side == "黑":
            for player in self.black_teams:
                reply.append(At(qq=player[0]))
        else:
            for player in self.white_teams:
                reply.append(At(qq=player[0]))
        return reply 

    def decrypt(self, password: str):
        reply = []
        if self.phase == 1: # 敌方解密阶段
            self.enemy_password = password
            self.phase = 2
            if self.turn % 2 == 1: # 黑方加密，白方完成解密，轮到黑方解密
                decrypt_side = "黑"
            else:
                decrypt_side = "白"
            reply.append(Plain(f"请{decrypt_side}队进行破解！"))
            for player in (self.black_teams if decrypt_side == "黑" else self.white_teams):
                reply.append(At(qq=player[0]))
        elif self.phase == 2: # 我方解密阶段
            self.phase = 0
            self.ally_password = password
            reply = self.turn_close()
        return reply

    def turn_close(self):
        reply = []
        reply.append(Plain(f"回合结束！本回合密码为：{self.password}"))
        if self.turn % 2 == 1: # 黑方加密
            self.black_history_ciphers.append(self.black_cipher)
            if self.enemy_password == self.password: # 白方猜测正确，拦截指示物+1
                self.white_intercepts += 1
                reply.append(Plain("\n\n白方破解成功！"))
            if self.ally_password != self.password: # 黑方猜测错误，错译指示物+1
                self.black_errors += 1
                reply.append(Plain("\n\n黑方译码失败！"))
        else: # 白方加密
            self.white_history_ciphers.append(self.white_cipher)
            if self.enemy_password == self.password: # 黑方猜测正确，拦截指示物+1
                self.black_intercepts += 1
                reply.append(Plain("\n\n黑方破解成功！"))
            if self.ally_password != self.password: # 黑方猜测错误，错译指示物+1
                self.white_errors += 1
                reply.append(Plain("\n\n白方译码失败！"))
        return reply
    
    def generate_note_dictionary(self):
        dictionary = {
            "black_history_ciphers": self.black_history_ciphers,
            "white_history_ciphers": self.white_history_ciphers,
            "black_teams": self.black_teams,
            "white_teams": self.white_teams,
            "black_intercepts": self.black_intercepts,
            "white_intercepts": self.white_intercepts,
            "black_errors": self.black_errors,
            "white_errors": self.white_errors,
            "is_game_set": self.is_game_set,
            "black_keywords": self.black_keywords,
            "white_keywords": self.white_keywords
            }
        return dictionary

    def game_set(self):
        # 指示物达标胜利
        if self.black_intercepts == 2:
            self.is_game_set = True
            self.game_set_reply = "黑方已拦截成功两次，获得胜利！"
        if self.white_intercepts == 2:
            self.is_game_set = True
            self.game_set_reply = "白方已拦截成功两次，获得胜利！"
        if self.black_errors == 2:
            self.is_game_set = True
            self.game_set_reply = "黑方已译码失败两次，白方获得胜利！"
        if self.white_errors == 2:
            self.is_game_set = True
            self.game_set_reply = "白方已译码失败两次，黑方获得胜利！"

        # 游戏结束积分胜利
        if self.turn == self.max_turns:
            self.is_game_set = True
            black_score = self.black_intercepts - self.black_errors
            white_score = self.white_intercepts - self.white_errors
            self.game_set_reply = f"游戏结束！\n黑方得分：{black_score}\n白方得分：{white_score}"
            if black_score > white_score:
                self.game_set_reply += "\n\n黑方获得胜利！"
            elif black_score < white_score:
                self.game_set_reply += "\n\n白方获得胜利！"
            else:
                self.game_set_reply += "\n\n双方达成平局！"
        
        if self.is_game_set:
            self.game_set_reply += "\n\n黑方关键字：" + ", ".join(self.black_keywords)
            self.game_set_reply += "\n\n白方关键字：" + ", ".join(self.white_keywords)

    def _generate_password(self):
        numbers = [1, 2, 3, 4]
        while True:
            elements = random.sample(numbers, 3)
            random.shuffle(elements)
            password = "".join(list(map(str, elements)))
            if password not in self.history_passwords:
                break
        self.history_passwords.append(password)
        self.password = password
    
    def _generate_keyword(self):
        available_keywords = list(set(self.keywords) - set(self.history_keywords))
        if len(available_keywords) < 8:
            available_keywords = self.keywords
            self.history_keywords = []
        elements = random.sample(available_keywords, 8)
        random.shuffle(elements)
        self.history_keywords += elements
        self.black_keywords = elements[0:4]
        self.white_keywords = elements[4:8]
    
    def _generate_new_keywords(self, team: str):
        available_keywords = list(set(self.keywords) - set(self.history_keywords))
        if len(available_keywords) < 4:
            self.history_keywords = []
            if team == "黑" or team == "black":
                self.history_keywords += self.white_keywords
            else:
                self.history_keywords += self.black_keywords
            available_keywords = list(set(self.keywords) - set(self.history_keywords))
        elements = random.sample(available_keywords, 4)
        random.shuffle(elements)
        self.history_keywords += elements
        if team == "黑" or team == "black":
            self.black_keywords = elements
        else:
            self.white_keywords = elements

@register("截码战Decrypto", "Garrise", "截码战桌游插件", "1.1.0")
class DecryptoPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""
        self.sessions = {}
        self.group_locks = defaultdict(asyncio.Lock)
        self.decrypt_timeout = self.config.get("decrypt_timeout", 300)  # 默认解密阶段超时300秒/5分钟
        self.encrypt_timeout = self.config.get("encrypt_timeout", 1800)  # 默认加密阶段总超时1800秒/30分钟
        self.timeout_tasks = {}
        self.remaining_time = {}

    async def _start_timeout_task(self, session_id: str):
        #检查先前的超时任务，如果有，取消它
        if session_id in self.timeout_tasks:
            task = self.timeout_tasks[session_id]
            if not task.done():
                task.cancel()
        #获取当前游戏进程
        if session_id in self.sessions:
            session: DecryptoSession = self.sessions[session_id]
        else:
            return
        async def time_reminder(remaining):
            while remaining > 0:

                await asyncio.sleep(1)
                remaining -= 1

                if remaining % 300 == 0:
                    minutes_left = remaining // 60
                    if minutes_left > 0:
                        await self.context.send_message(f"default:GroupMessage:{session_id}", MessageChain().message(f"剩余{minutes_left}分钟！"))
                if remaining == 120:
                    await self.context.send_message(f"default:GroupMessage:{session_id}", MessageChain().message("剩余2分钟！"))
        async def timeout_handler():
            #加密阶段
            if session.phase == 0:
                if session.turn % 2 == 0: #白方加密
                    # 剩余时间提醒
                    await self.context.send_message(f"default:GroupMessage:{session_id}", MessageChain().message(f"剩余时间：{session.white_timeout // 60}分钟！"))
                    remaining = session.white_timeout

                    await time_reminder(remaining)
                    
                    session.is_game_set = True
                    session.game_set_reply = "截码战游戏加密阶段超时，白方未能在规定时间内完成加密，黑方获得胜利！"
                    dictionary = session.generate_note_dictionary()
                    tmpl_path = Path(__file__).parent / "template/note.html"
                    options = {
                        "type": "jpeg",
                        "quality": 90
                    }
                    with open(str(tmpl_path), "r", encoding="utf-8") as f:
                        tmpl_str = f.read()
                    url = await self.html_render(tmpl_str, dictionary, options=options)
                    await self.context.send_message(f"default:GroupMessage:{session_id}", MessageChain().message(session.game_set_reply))
                    await self.context.send_message(f"default:GroupMessage:{session_id}", MessageChain().url_image(url))
                    del self.timeout_tasks[session_id]
                    del self.sessions[session_id]
                else: #黑方加密
                    # 剩余时间提醒
                    await self.context.send_message(f"default:GroupMessage:{session_id}", MessageChain().message(f"剩余时间：{session.black_timeout // 60}分钟！"))
                    remaining = session.black_timeout
                    
                    await time_reminder(remaining)

                    session.is_game_set = True
                    session.game_set_reply = "截码战游戏加密阶段超时，黑方未能在规定时间内完成加密，白方获得胜利！"
                    dictionary = session.generate_note_dictionary()
                    tmpl_path = Path(__file__).parent / "template/note.html"
                    options = {
                        "type": "jpeg",
                        "quality": 90
                    }
                    with open(str(tmpl_path), "r", encoding="utf-8") as f:
                        tmpl_str = f.read()
                    url = await self.html_render(tmpl_str, dictionary, options=options)
                    await self.context.send_message(f"default:GroupMessage:{session_id}", MessageChain().message(session.game_set_reply))
                    await self.context.send_message(f"default:GroupMessage:{session_id}", MessageChain().url_image(url))
                    del self.timeout_tasks[session_id]
                    del self.sessions[session_id]
            elif session.phase == 1: #敌方截码阶段
                await self.context.send_message(f"default:GroupMessage:{session_id}", MessageChain().message(f"剩余时间：{self.decrypt_timeout // 60}分钟！"))
                remaining = self.decrypt_timeout

                await time_reminder(remaining)

                session.enemy_password = "000" #默认猜测错误
                session.phase = 2
                if session.turn % 2 == 0: #白方加密，黑方截码
                    message_chain = MessageChain().message("黑方解密超时，轮到白方进行译码！")
                    for player in session.white_teams:
                        message_chain.at(player[1], player[0])
                else: #黑方加密，白方截码
                    message_chain = MessageChain().message("白方解密超时，轮到黑方进行译码！")
                    for player in session.black_teams:
                        message_chain.at(player[1], player[0])
                await self.context.send_message(f"default:GroupMessage:{session_id}", message_chain)
                await self._start_timeout_task(session_id)
            elif session.phase == 2: #我方译码阶段
                await self.context.send_message(f"default:GroupMessage:{session_id}", MessageChain().message(f"剩余时间：{self.decrypt_timeout // 60}分钟！"))
                remaining = self.decrypt_timeout

                await time_reminder(remaining)
                
                session.phase = 0
                session.ally_password = "000" #默认猜测错误
                if session.turn % 2 == 0: #白方加密，白方译码
                    message_chain = MessageChain().message("白方解密超时，回合结束！")
                else: #黑方加密，黑方译码
                    message_chain = MessageChain().message("黑方解密超时，回合结束！")
                await self.context.send_message(f"default:GroupMessage:{session_id}", message_chain)
                # 回合结算
                reply = session.turn_close()
                await self.context.send_message(f"default:GroupMessage:{session_id}", MessageChain(reply))
                # 胜负判断
                session.game_set()
                if session.is_game_set:
                    dictionary = session.generate_note_dictionary()
                    tmpl_path = Path(__file__).parent / "template/note.html"
                    options = {
                        "type": "jpeg",
                        "quality": 90
                    }
                    with open(str(tmpl_path), "r", encoding="utf-8") as f:
                        tmpl_str = f.read()
                    url = await self.html_render(tmpl_str, dictionary, options=options)
                    await self.context.send_message(f"default:GroupMessage:{session_id}", MessageChain().message(session.game_set_reply))
                    await self.context.send_message(f"default:GroupMessage:{session_id}", MessageChain().url_image(url))
                    del self.timeout_tasks[session_id]
                    del self.sessions[session_id]
                else:
                    reply = session.turn_change()
                    await self.context.send_message(f"default:GroupMessage:{session_id}", MessageChain(reply))
                    await self.context.send_message(f"default:FriendMessage:{session.encrypter}", MessageChain().message(f"你的密码是：{session.password}")) 
                    await self._start_timeout_task(session_id)
        task = asyncio.create_task(timeout_handler())
        self.timeout_tasks[session_id] = task
        logger.info(f"Started timeout task for session {session_id}")

    # 注册指令的装饰器。指令名为 helloworld。注册成功后，发送 `/helloworld` 就会触发这个指令，并回复 `你好, {user_name}!`
    @filter.command("截码战", alias={"decrypto"})
    async def decrypto_invite(self, event: AstrMessageEvent):
        session_id = event.get_group_id()
        if session_id == "":
            return
        async with self.group_locks[session_id]:
            if session_id in self.sessions:
                yield event.plain_result(f"截码战游戏正在运行中")
                event.stop_event()
                return
            session = DecryptoSession(self.decrypt_timeout, self.encrypt_timeout)
            self.sessions[session_id] = session
            yield event.plain_result('''
截码战开始招募特工！
【请保证已经添加机器人为好友】
参加指令：
/截码 加入 [黑/白/随机]
/dc join [black/white/random]
            '''.strip())

    @filter.command_group("截码", alias={"dc"})
    def decrypto():
        pass

    @decrypto.command("加入", alias={"join"})
    async def join(self, event: AstrMessageEvent, team: str):
        session_id = event.get_group_id()
        if session_id == "":
            return
        async with self.group_locks[session_id]:
            if session_id not in self.sessions:
                session = DecryptoSession(self.decrypt_timeout, self.encrypt_timeout)
                self.sessions[session_id] = session
                yield event.plain_result('''
截码战开始招募特工！
参加指令：
/截码 加入 [黑/白/随机]
/dc join [black/white/random]
            '''.strip())
            black_cmd = ["黑", "black"]
            white_cmd = ["白", "white"]
            random_cmd = ["随机", "random"]
            session: DecryptoSession = self.sessions[session_id]
            if session.start_flag:
                yield event.plain_result("游戏已经开始，无法加入！")
                event.stop_event
                return
            if event.get_sender_id() in session.black_teams or event.get_sender_id() in session.white_teams:
                yield event.plain_result(f"你已经加入了一个队伍！")
                event.stop_event()
                return
            if team in black_cmd:
                if len(session.black_teams) < 4:
                    session.black_teams.append((event.get_sender_id(), event.get_sender_name()))
                    yield event.plain_result(f"{event.get_sender_name()}加入了黑队！")
                else:
                    yield event.plain_result(f"黑队人数已满，无法加入！")
            elif team in white_cmd:
                if len(session.white_teams) < 4:
                    session.white_teams.append((event.get_sender_id(), event.get_sender_name()))
                    yield event.plain_result(f"{event.get_sender_name()}加入了白队！")
                else:
                    yield event.plain_result(f"白队人数已满，无法加入！")
            elif team in random_cmd:
                if len(session.black_teams) < 4 and len(session.white_teams) < 4:
                    if len(session.black_teams) < len(session.white_teams):
                        session.black_teams.append((event.get_sender_id(), event.get_sender_name()))
                        yield event.plain_result(f"{event.get_sender_name()}加入了黑队！")
                    elif len(session.white_teams) < len(session.black_teams):
                        session.white_teams.append((event.get_sender_id(), event.get_sender_name()))
                        yield event.plain_result(f"{event.get_sender_name()}加入了白队！")
                    else:
                        coin = random.randint(0, 1)
                        if coin:
                            session.black_teams.append((event.get_sender_id(), event.get_sender_name()))
                            yield event.plain_result(f"{event.get_sender_name()}加入了黑队！")
                        else:
                            session.white_teams.append((event.get_sender_id(), event.get_sender_name()))
                            yield event.plain_result(f"{event.get_sender_name()}加入了白队！")
                elif len(session.black_teams) < 4:
                    session.black_teams.append((event.get_sender_id(), event.get_sender_name()))
                    yield event.plain_result(f"{event.get_sender_name()}加入了黑队！")
                elif len(session.white_teams) < 4:
                    session.white_teams.append((event.get_sender_id(), event.get_sender_name()))
                    yield event.plain_result(f"{event.get_sender_name()}加入了白队！")
                else:
                    yield event.plain_result(f"队伍人数已满，无法加入！")
            event.stop_event()
    
    @decrypto.command("开始", alias={"start"})
    async def start(self, event: AiocqhttpMessageEvent, mode: str = "random"):
        session_id = event.get_group_id()
        if session_id == "":
            return
        if session_id not in self.sessions:
            yield event.plain_result(f"截码战尚未开始！")
            event.stop_event()
            return
        async with self.group_locks[session_id]:
            session: DecryptoSession = self.sessions[session_id]
            if session.start_flag or session.keywords_sent:
                event.stop_event()
                return
            if len(session.black_teams) < 2 or len(session.white_teams) < 2:
                yield event.plain_result("每队至少需要2名成员才能开始游戏！")
                event.stop_event()
                return
            #判断玩家是否都是好友
            reply = "以下玩家不是机器人的好友，无法开始游戏："
            not_friends = []
            for member_id, member_name in session.black_teams + session.white_teams:
                is_friend = False
                friend_list = await event.bot.call_action("get_friend_list")
                for friend in friend_list:
                    if member_id == str(friend.get("user_id")):
                        is_friend = True
                        break
                if not is_friend:
                    not_friends.append(member_name)
            if not_friends:
                yield event.plain_result(reply + "\n" + "\n".join(f"- {name}" for name in not_friends))
                event.stop_event()
                return
                    
            reply = session.game_start()
            yield event.plain_result(reply)

            if mode.lower() == "custom" or mode.lower() == "自定义":
                #等待法官私聊关键字
                session.custom_keywords = True
                yield event.plain_result("请法官私聊机器人发送关键字。\n格式：\n/截码 自定义 [群号] 黑队关键词1,黑队关键词2,黑队关键词3,黑队关键词4|白队关键词1,白队关键词2,白队关键词3,白队关键词4")
                return
            else:
                #分发关键字
                for member_id, _  in session.black_teams:
                    print(f"发送黑队关键字给{member_id}")
                    await self.context.send_message(f"default:FriendMessage:{member_id}", MessageChain().message(f"关键字：{', '.join(session.black_keywords)}"))
                for member_id, _  in session.white_teams:
                    print(f"发送白队关键字给{member_id}")
                    await self.context.send_message(f"default:FriendMessage:{member_id}", MessageChain().message(f"关键字：{', '.join(session.white_keywords)}"))
                session.keywords_sent = True

    @decrypto.command("自定义", alias={"custom"})
    async def custom_keywords(self, event: AstrMessageEvent, group_id: str, keywords: str):
        session_id = group_id
        if not event.is_private_chat():
            yield event.plain_result("请私聊机器人发送关键字！")
            event.stop_event()
            return
        if session_id not in self.sessions:
            yield event.plain_result("截码战尚未开始！")
            event.stop_event()
            return
        async with self.group_locks[session_id]:
            session: DecryptoSession = self.sessions[session_id]
            if not session.custom_keywords:
                yield event.plain_result("本局游戏不使用自定义关键字！")
                event.stop_event()
                return
            sender_id = event.get_sender_id()
            is_judge = True
            for member in session.black_teams + session.white_teams:
                if sender_id == member[0]:
                    is_judge = False
                    break
            if not is_judge:
                yield event.plain_result("玩家不能设置关键字！")
                event.stop_event()
                return
            if session.custom_keywords_set:
                yield event.plain_result("关键字已经设置！")
                event.stop_event()
                return
            else:
                if "|" not in keywords:
                    yield event.plain_result("关键字格式错误！\n格式：\n黑队关键词1,黑队关键词2,黑队关键词3,黑队关键词4|白队关键词1,白队关键词2,白队关键词3,白队关键词4")
                    event.stop_event()
                    return
                if "," not in keywords.split("|")[0] or "," not in keywords.split("|")[1]:
                    yield event.plain_result("关键字格式错误！\n格式：\n黑队关键词1,黑队关键词2,黑队关键词3,黑队关键词4|白队关键词1,白队关键词2,白队关键词3,白队关键词4")
                    event.stop_event()
                    return
                black_keywords = keywords.split("|")[0].split(",")
                white_keywords = keywords.split("|")[1].split(",")
                if len(black_keywords) != 4 or len(white_keywords) != 4:
                    yield event.plain_result("关键字数量错误，请确保每队有4个关键字！")
                    event.stop_event()
                    return
                for keyword in black_keywords + white_keywords:
                    if " " in keyword:
                        yield event.plain_result("关键字不能包含空格！")
                        event.stop_event()
                        return
                session.black_keywords = black_keywords
                session.white_keywords = white_keywords
                #分发关键字
                for member_id, _  in session.black_teams:
                    print(f"发送黑队关键字给{member_id}")
                    await self.context.send_message(f"default:FriendMessage:{member_id}", MessageChain().message(f"关键字：{', '.join(session.black_keywords)}"))
                for member_id, _  in session.white_teams:
                    print(f"发送白队关键字给{member_id}")
                    await self.context.send_message(f"default:FriendMessage:{member_id}", MessageChain().message(f"关键字：{', '.join(session.white_keywords)}"))
                session.custom_keywords_set = True
                session.keywords_sent = True
                yield event.plain_result("关键字已设置！")

    @decrypto.command("关键字", alias={"keywords"})
    async def keywords(self, event: AstrMessageEvent, confirmed: str):
        session_id = event.get_group_id()
        if session_id == "":
            return
        if session_id not in self.sessions:
            yield event.plain_result("截码战尚未开始！")
            event.stop_event()
            return
        async with self.group_locks[session_id]:
            session: DecryptoSession = self.sessions[session_id]
            if session.start_flag:
                yield event.plain_result("游戏已经开始！无法处理关键字！")
                event.stop_event()
                return
            if not session.keywords_sent:
                yield event.plain_result("关键字尚未发送！")
                event.stop_event()
                return
            if confirmed.lower() == "确认" or confirmed.lower() == "confirm":
                sender_id = event.get_sender_id()
                if any(member[0] == sender_id for member in session.black_teams):
                    session.black_confirmed = True
                    yield event.plain_result("黑队关键字确认完成！")
                elif any(member[0] == sender_id for member in session.white_teams):
                    session.white_confirmed = True
                    yield event.plain_result("白队关键字确认完成！")
                else:
                    yield event.plain_result("你不在任何队伍中！")
                if session.black_confirmed and session.white_confirmed:
                    session.start_flag = True
                    yield event.plain_result("双方关键字均已确认，游戏正式开始！")
                    # 宣告第一回合，并发送密码
                    reply = session.turn_change()
                    yield event.chain_result(reply)
                    await self.context.send_message(f"default:FriendMessage:{session.encrypter}", MessageChain().message(f"你的密码是：{session.password}"))
                    # 开始计时
                    session.encrypt_start_time = int(time.perf_counter())
                    await self._start_timeout_task(session_id)
            elif confirmed.lower() == "重抽" or confirmed.lower() == "reroll":
                sender_id = event.get_sender_id()
                if any(member[0] == sender_id for member in session.black_teams):
                    if session.black_confirmed:
                        yield event.plain_result("黑队关键字已确认，无法重抽！")
                        return
                    if session.custom_keywords:
                        session.custom_keywords_set = False
                        session.keywords_sent = False
                        yield event.plain_result("关键字已作废，请法官重新发送关键字！")
                        return
                    else:
                        session._generate_new_keywords("黑")
                        for member in session.black_teams:
                            await self.context.send_message(f"default:FriendMessage:{member[0]}", MessageChain().message(f"新的关键字：{', '.join(session.black_keywords)}"))
                        yield event.plain_result("黑队关键字已重抽并发送，请查收私信！")
                elif any(member[0] == sender_id for member in session.white_teams):
                    if session.white_confirmed:
                        yield event.plain_result("白队关键字已确认，无法重抽！")
                        return
                    if session.custom_keywords:
                        session.custom_keywords_set = False
                        session.keywords_sent = False
                        yield event.plain_result("关键字已作废，请法官重新发送关键字！")
                        return
                    else:
                        session._generate_new_keywords("白")
                        for member in session.white_teams:
                            await self.context.send_message(f"default:FriendMessage:{member[0]}", MessageChain().message(f"新的关键字：{', '.join(session.white_keywords)}"))
                        yield event.plain_result("白队关键字已重抽并发送，请查收私信！")
                else:
                    yield event.plain_result("你不在任何队伍中！")
            

    @decrypto.command("加密", alias={"encrypt"})
    async def encrypt(self, event: AstrMessageEvent, cipher1: str, cipher2: str, cipher3: str):
        session_id = event.get_group_id()
        if session_id == "":
            return
        if session_id not in self.sessions:
            yield event.plain_result("截码战尚未开始！")
            event.stop_event()
            return
        async with self.group_locks[session_id]:
            session: DecryptoSession = self.sessions[session_id]
            if not session.start_flag:
                yield event.plain_result("截码战尚未开始！")
                event.stop_event()
                return
            if session.phase != 0:
                yield event.plain_result("现在不是加密阶段！")
                event.stop_event()
                return            
            sender_id = event.get_sender_id()
            if sender_id != session.encrypter:
                yield event.plain_result("你不是加密员！")
                event.stop_event()
                return
            
            reply = session.encrypt(cipher1, cipher2, cipher3)
            yield event.chain_result(reply)
            # 停止计时
            encrypt_end_time = int(time.perf_counter())
            elapsed_time = encrypt_end_time - session.encrypt_start_time
            if session.turn % 2 == 0: #白方加密
                session.white_timeout = session.white_timeout - elapsed_time
            else: #黑方加密
                session.black_timeout = session.black_timeout - elapsed_time
            # 开始解密阶段超时任务
            await self._start_timeout_task(session_id)


    @decrypto.command("解密", alias=["decrypt"])
    async def decrypt(self, event: AstrMessageEvent, password: str):
        session_id = event.get_group_id()
        if session_id == "":
            return
        if session_id not in self.sessions:
            yield event.plain_result("截码战尚未开始！")
            event.stop_event()
            return
        async with self.group_locks[session_id]:
            session: DecryptoSession = self.sessions[session_id]
            if not session.start_flag:
                yield event.plain_result("截码战尚未开始！")
                event.stop_event()
                return         
            sender_id = event.get_sender_id()
            if sender_id == session.encrypter:
                yield event.plain_result("加密员请保持沉默！")
                event.stop_event()
                return
            if ((session.turn + session.phase) % 2 == 0 and any(member[0] == sender_id for member in session.white_teams)) or \
                ((session.turn + session.phase) % 2 == 1 and any(member[0] == sender_id for member in session.black_teams)):
                reply = session.decrypt(password)
                if reply:
                    yield event.chain_result(reply)
            else:
                yield event.plain_result("还没有轮到你方解密！")

            if session.phase == 0: # 回合转换，发送密码和笔记
                session.game_set()
                dictionary = session.generate_note_dictionary()
                tmpl_path = Path(__file__).parent / "template/note.html"
                options = {
                    "type": "jpeg",
                    "quality": 90
                }
                with open(str(tmpl_path), "r", encoding="utf-8") as f:
                    tmpl_str = f.read()
                url = await self.html_render(tmpl_str, dictionary, options=options)
                yield event.image_result(url)
                if not session.is_game_set: #游戏还没结束
                    reply = session.turn_change()
                    yield event.chain_result(reply)
                    await self.context.send_message(f"default:FriendMessage:{session.encrypter}", MessageChain().message(f"你的密码是：{session.password}"))
                    # 开始计时
                    session.encrypt_start_time = int(time.perf_counter())
                    await self._start_timeout_task(session_id)
                else: 
                    yield event.plain_result(session.game_set_reply)
                    del self.sessions[session_id]
                    del self.group_locks[session_id]
                    task = self.timeout_tasks[session_id]
                    if not task.done():
                        task.cancel()
                    del self.timeout_tasks[session_id]
            else: # 回合没转换
                await self._start_timeout_task(session_id)
            event.stop_event()

    @decrypto.command("查询", alias=["info"])
    async def info(self, event: AstrMessageEvent):
        session_id = event.get_group_id()
        if session_id == "":
            return
        if session_id not in self.sessions:
            yield event.plain_result("截码战尚未开始！")
            event.stop_event()
            return
        async with self.group_locks[session_id]:
            session: DecryptoSession = self.sessions[session_id]
            dictionary = session.generate_note_dictionary()
            options = {
                "type": "jpeg",
                "quality": 90
            }
            tmpl_path = Path(__file__).parent / "template/note.html"
            with open(str(tmpl_path), "r", encoding="utf-8") as f:
                tmpl_str = f.read()
            url = await self.html_render(tmpl_str, dictionary, options=options)
            yield event.image_result(url)

    @decrypto.command("终止", alias=["stop"])
    async def stop(self, event: AstrMessageEvent):
        session_id = event.get_group_id()
        if session_id == "":
            return
        if session_id not in self.sessions:
            yield event.plain_result("截码战尚未开始！")
            event.stop_event()
            return
        async with self.group_locks[session_id]:
            del self.sessions[session_id]
            del self.group_locks[session_id]
            yield event.plain_result("截码战已终止。")
            event.stop_event()

    @decrypto.command("帮助", alias=["help"])
    async def help(self, event: AstrMessageEvent):
        help_text = '''
截码战Decrypto插件帮助：
"/截码 加入 [黑/白/随机]" 或 "/dc join [black/white/random]"
  加入黑队或白队，或随机加入。

"/截码 开始" 或 "/dc start"
  开始截码战游戏，分配关键字。

"/截码 开始 自定义" 或 "/dc start custom"
  开始截码战游戏，使用自定义关键字。随后请非玩家私聊机器人设置关键字！

"/截码 关键字 [重抽/确认]" 或 "/dc keywords [reroll/confirm]"
  关键字确认或重抽指令，只有在游戏开始前可以使用。

"/截码 加密 [密文1] [密文2] [密文3]" 或 "/dc encrypt [cipher1] [cipher2] [cipher3]"
  加密指令，只有加密员可以使用。

"/截码 解密 [密码]" 或 "/dc decrypt [password]"
  解密指令，非加密员可以使用。

"/截码 查询" 或 "/dc info"
  查询当前游戏状态和笔记。

"/截码 终止" 或 "/dc stop"
  终止当前游戏。'''
        yield event.plain_result(help_text)

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""