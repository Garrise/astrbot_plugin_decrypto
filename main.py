from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult, MessageChain
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.all import AstrBotConfig, Image, Plain

import random, math
from pathlib import Path

class DecryptoSession():
    def __init__(self):            
        with open(Path(__file__).parent / "keywords.txt", "r", encoding="utf-8") as f:
            self.keywords = f.read().split(",")
        self.history_keywords = []
        self.history_passwords = []
        self.black_teams = []
        self.white_teams = []
        self._generate_keyword()

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

        # 状态标识
        self.start_flag = False
        self.game_set = False
        self.game_set_reply = ""

    def shuffle_teams(self):
        random.shuffle(self.black_teams)
        random.shuffle(self.white_teams)

    def game_start(self, event: AstrMessageEvent):
        self.start_flag = True
        self.shuffle_teams()
        start_reply = "截码战正式开始！"
        start_reply += "\n\n【黑队】"
        for index, member in enumerate(self.black_teams, start = 1):
            start_reply += f"\n{index}. {member[1]}"
        start_reply += "\n\n【白队】"
        for index, member in enumerate(self.white_teams, start = 1):
            start_reply += f"\n{index}. {member[1]}"
        yield event.plain_result(start_reply)


    def turn_change(self, event: AstrMessageEvent):
        self.turn += 1
        turn = math.ceil(self.turn / 2)
        reply = f"第{turn}回合，"
        
        if self.turn % 2 == 1:
            self.encrypter = self.black_teams[turn][0]
            reply += f"黑方加密员：{self.black_teams[turn][1]}"
        else:
            self.encrypter = self.white_teams[turn][0]
            reply += f"白方加密员：{self.white_teams[turn][1]}"
        reply += "\n输入指令进行加密：\n/截码 加密 [密文1] [密文2] [密文3]\n/dc encrypt [cipher1] [cipher2] [cipher3]"
        self.phase = 0

        yield event.plain_result(reply)

        # 私聊密码
        self._generate_password()

    def encrypt(self, event: AstrMessageEvent, cipher1: str, cipher2: str, cipher3: str):
        ciphers = [cipher1, cipher2, cipher3]
        cipher_record = [""] * 4
        for i, cipher in zip(self.password, ciphers):
            cipher_record[int(i) - 1] = cipher
        if self.turn % 2 == 1:
            self.black_history_ciphers.append(cipher_record)
            decrypt_side = "白"
        else:
            self.white_history_ciphers.append(cipher_record)
            decrypt_side = "黑"

        self.phase = 1
        yield event.plain_result(f"加密完成！\n请{decrypt_side}队输入指令进行破解：\n/截码 解密 [密码]\n/dc decrypt [password]")

    def decrypt(self, event: AstrMessageEvent, password: str):
        if self.phase == 1: # 敌方解密阶段
            self.enemy_password = password
            self.phase = 2
            if self.turn % 2 == 1: # 黑方加密，白方完成解密，轮到黑方解密
                decrypt_side = "黑"
            else:
                decrypt_side = "白"
            yield event.plain_result(f"请{decrypt_side}队输入指令进行破解：\n/截码 解密 [密码]\n/dc decrypt [password]")
        elif self.phase == 2: # 我方解密阶段
            self.ally_password = password
            yield self.turn_close(event)

    def turn_close(self, event: AstrMessageEvent):
        reply = f"回合结束！本回合密码为：{self.password}"
        if self.turn % 2 == 1: # 黑方加密
            if self.enemy_password == self.password: # 白方猜测正确，拦截指示物+1
                self.white_intercepts += 1
                reply += f"\n\n白方破解成功！"
            if self.ally_password != self.password: # 黑方猜测错误，错译指示物+1
                self.black_errors += 1
                reply += f"\n\n黑方译码失败！"
        else: # 白方加密
            if self.enemy_password == self.password: # 黑方猜测正确，拦截指示物+1
                self.black_intercepts += 1
                reply += f"\n\n黑方破解成功！"
            if self.ally_password != self.password: # 黑方猜测错误，错译指示物+1
                self.white_errors += 1
                reply += f"\n\n白方译码失败！"
        if not self._game_set(): #游戏还没结束
            self.turn_change(event)
        yield event.plain_result(reply)
    
    def generate_note_dictionary(self):
        dictionary = {
            "black_history_ciphers": self.black_history_ciphers,
            "white_history_ciphers": self.white_history_ciphers,
            "black_teams": self.black_teams,
            "white_teams": self.white_teams
            }
        return dictionary

    def _game_set(self):
        # 指示物达标胜利
        if self.black_intercepts == 2:
            self.game_set = True
            self.game_set_reply = "黑方已拦截成功两次，获得胜利！"
            return True
        if self.white_intercepts == 2:
            self.game_set = True
            self.game_set_reply = "白方已拦截成功两次，获得胜利！"
            return True
        if self.black_errors == 2:
            self.game_set = True
            self.game_set_reply = "黑方已译码失败两次，白方获得胜利！"
            return True
        if self.white_errors == 2:
            self.game_set = True
            self.game_set_reply = "白方已译码失败两次，黑方获得胜利！"
            return True

        # 游戏结束积分胜利
        if self.turn == 16:
            self.game_set = True
            black_score = self.black_intercepts - self.black_errors
            white_score = self.white_intercepts - self.white_errors
            self.game_set_reply = f"游戏结束！\n黑方得分：{black_score}\n白方得分：{white_score}"
            if black_score > white_score:
                self.game_set_reply += "\n\n黑方获得胜利！"
            elif black_score < white_score:
                self.game_set_reply += "\n\n白方获得胜利！"
            else:
                self.game_set_reply += "\n\n双方达成平局！"
            return True
        return False

    def _generate_password(self):
        numbers = [1, 2, 3, 4]
        while password not in self.history_passwords:
            elements = random.sample(numbers, 3)
            random.shuffle(elements)
            password = "".join(list(map(str, elements)))
        self.history_passwords.append(password)
        self.password = password
    
    def _generate_keyword(self):
        available_keywords = list(set(self.keywords) - set(self.history_keywords))
        if len(available_keywords) < 8:
            available_keywords = self.keywords
            self.history_keywords = []
        elements = random.sample(available_keywords, 8)
        random.shuffle(elements)
        self.history_keywords.append(elements)
        self.black_keywords = elements[0:4]
        self.white_keywords = elements[4:8]

@register("截码战Decrypto", "Garrise", "截码战桌游插件", "1.0.0")
class DecryptoPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""
        self.sessions = {}

    # 注册指令的装饰器。指令名为 helloworld。注册成功后，发送 `/helloworld` 就会触发这个指令，并回复 `你好, {user_name}!`
    @filter.command("截码战", alias={"decrypto"})
    async def decrypto_invite(self, event: AstrMessageEvent):
        session_id = event.get_group_id()
        if session_id == "":
            return
        if session_id in self.sessions:
            yield event.plain_result(f"截码战游戏正在运行中")
            event.stop_event()
            return
        session = DecryptoSession()
        self.sessions[session_id] = session
        yield event.plain_result('''
截码战开始招募特工！
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
        if session_id not in self.sessions:
            yield event.plain_result(f"截码战尚未开始！")
            event.stop_event()
            return
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
                yield event.plain_result(f"{event.get_sender_id()}加入了黑队！")
            else:
                yield event.plain_result(f"黑队人数已满，无法加入！")
        elif team in white_cmd:
            if len(session.white_teams) < 4:
                session.white_teams.append((event.get_sender_id(), event.get_sender_name()))
                yield event.plain_result(f"{event.get_sender_id()}加入了白队！")
            else:
                yield event.plain_result(f"白队人数已满，无法加入！")
        elif team in random_cmd:
            if len(session.black_teams) < 4 and len(session.white_teams) < 4:
                coin = random.randint(0, 1)
                if coin:
                    session.black_teams.append((event.get_sender_id(), event.get_sender_name()))
                    yield event.plain_result(f"{event.get_sender_id()}加入了黑队！")
                else:
                    session.white_teams.append((event.get_sender_id(), event.get_sender_name()))
                    yield event.plain_result(f"{event.get_sender_id()}加入了白队！")
            elif len(session.black_teams) < 4:
                session.black_teams.append((event.get_sender_id(), event.get_sender_name()))
                yield event.plain_result(f"{event.get_sender_id()}加入了黑队！")
            elif len(session.white_teams) < 4:
                session.white_teams.append((event.get_sender_id(), event.get_sender_name()))
                yield event.plain_result(f"{event.get_sender_id()}加入了白队！")
            else:
                yield event.plain_result(f"队伍人数已满，无法加入！")
        event.stop_event()
    
    @decrypto.command("开始", alias={"start"})
    async def start(self, event: AstrMessageEvent):
        session_id = event.get_group_id()
        if session_id == "":
            return
        if session_id not in self.sessions:
            yield event.plain_result(f"截码战尚未开始！")
            event.stop_event()
            return
        session: DecryptoSession = self.sessions[session_id]
        if session.start_flag:
            event.stop_event()
            return
        
        yield session.game_start(event)

        #分发关键字
        for member_id, _  in session.black_teams:
            await self.context.send_message(member_id, MessageChain().message(f"关键字：{', '.join(session.black_keywords)}"))
        for member_id, _  in session.white_teams:
            await self.context.send_message(member_id, MessageChain().message(f"关键字：{', '.join(session.white_keywords)}"))
        
        # 宣告第一回合，并发送密码
        yield session.turn_change(event)
        await self.context.send_message(session.encrypter, MessageChain().message(f"你的密码是：{session.password}"))

    @decrypto.command("加密", alias={"encrypt"})
    async def encrypt(self, event: AstrMessageEvent, cipher1: str, cipher2: str, cipher3: str):
        session_id = event.get_group_id()
        if session_id == "":
            return
        if session_id not in self.sessions:
            yield event.plain_result("截码战尚未开始！")
            event.stop_event()
            return
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
            event.stop_event
            return
        
        yield session.encrypt(event, cipher1, cipher2, cipher3)

    @decrypto.command("解密", alias=["decrypt"])
    async def decrypt(self, event: AstrMessageEvent, password: str):
        session_id = event.get_group_id()
        if session_id == "":
            return
        if session_id not in self.sessions:
            yield event.plain_result("截码战尚未开始！")
            event.stop_event()
            return
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
        if ((session.turn * session.phase) % 2 == 1 and any(member[0] == sender_id for member in session.white_teams)) or \
            ((session.turn * session.phase) % 2 == 0 and any(member[0] == sender_id for member in session.black_teams)):
            yield session.decrypt(event, password)
        else:
            yield event.plain_result("还没有轮到你方解密！")

        if session.phase == 0: # 回合转换，发送密码和笔记
            dictionary = session.generate_note_dictionary()
            tmpl_path = Path(__file__).parent / "template/note.html"
            url = await self.html_render(str(tmpl_path), dictionary)
            yield event.image_result(url)
        
        if session.game_set: # 游戏结束
            yield event.plain_result(session.game_set_reply)
            del self.sessions[session_id]
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
        session: DecryptoSession = self.sessions[session_id]
        dictionary = session.generate_note_dictionary()
        tmpl_path = Path(__file__).parent / "template/note.html"
        with open(str(tmpl_path), "r", encoding="utf-8") as f:
            tmpl_str = f.read()
        url = await self.html_render(tmpl_str, dictionary)
        yield event.image_result(url)
        
    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""