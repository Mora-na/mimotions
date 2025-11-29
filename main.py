# -*- coding: utf8 -*-
import math
import traceback
from datetime import datetime
import pytz
import uuid

import json
import random
import re
import time
import os

import requests
from util.aes_help import  encrypt_data, decrypt_data
import util.zepp_helper as zeppHelper

# 优先从账号专属配置读取，无则读根配置，最后用默认值（转int）
def get_int_value_default(account, _config: dict, _key, default):
    """
    获取配置值并转为int，优先级：
    1. STEP_RANGES[account][_key]
    2. _config[_key]
    3. default
    """
    # 1. 优先读取账号专属配置（STEP_RANGES）
    step_ranges = _config.get("STEP_RANGES", {})  # 兜底为空字典
    if isinstance(step_ranges, dict) and account in step_ranges:
        account_config = step_ranges[account]
        if isinstance(account_config, dict) and _key in account_config:
            return int(account_config[_key])  # 账号专属配置存在则返回
    
    # 2. 读取根节点配置
    if _key in _config:
        return int(_config[_key])
    
    # 3. 所有配置都不存在，返回默认值
    return int(default)


# 获取当前时间对应的最大和最小步数（适配账号专属配置）
def get_min_max_by_time(user_mi, _config: dict, hour=None, minute=None):
    """
    根据当前时间和配置（优先账号专属）返回步数范围：
    - 21:30前：MIN ~ 中间值
    - 21:30后：中间值 ~ MAX
    """
    
    # 自动获取当前北京时间（未传时分时）
    if hour is None:
        hour = time_bj.hour
    if minute is None:
        minute = time_bj.minute
    
    # 读取步数配置（优先账号专属）
    min_step = get_int_value_default(user_mi, _config, "MIN_STEP", 18000)
    max_step = get_int_value_default(user_mi, _config, "MAX_STEP", 25000)
    
    # 计算中间分界值
    mid_step = (min_step + max_step) // 2
    
    # 时间判断（21:30为分界点）
    TIME_2130 = 21 * 60 + 30  # 转换为总分钟数：1290
    current_total_min = hour * 60 + minute
    
    if current_total_min < TIME_2130:
        return min_step, mid_step  # 21:30前：MIN ~ 中间值
    else:
        return mid_step, max_step  # 21:30后：中间值 ~ MAX


# 虚拟ip地址
def fake_ip():
    # 随便找的国内IP段：223.64.0.0 - 223.117.255.255
    return f"{223}.{random.randint(64, 117)}.{random.randint(0, 255)}.{random.randint(0, 255)}"


# 账号脱敏
def desensitize_user_name(user):
    if len(user) <= 8:
        ln = max(math.floor(len(user) / 3), 1)
        return f'{user[:ln]}***{user[-ln:]}'
    return f'{user[:3]}****{user[-4:]}'


# 获取北京时间
def get_beijing_time():
    target_timezone = pytz.timezone('Asia/Shanghai')
    # 获取当前时间
    return datetime.now().astimezone(target_timezone)


# 格式化时间
def format_now():
    return get_beijing_time().strftime("%m-%d %H:%M")


# 获取时间戳
def get_time():
    current_time = get_beijing_time()
    return "%.0f" % (current_time.timestamp() * 1000)


# 获取登录code
def get_access_token(location):
    code_pattern = re.compile("(?<=access=).*?(?=&)")
    result = code_pattern.findall(location)
    if result is None or len(result) == 0:
        return None
    return result[0]


def get_error_code(location):
    code_pattern = re.compile("(?<=error=).*?(?=&)")
    result = code_pattern.findall(location)
    if result is None or len(result) == 0:
        return None
    return result[0]


# pushplus消息推送
def push_plus(title, content):
# pushdeer API地址（HTTPS）
    request_url = "https://api2.pushdeer.com/message/push"
    
    # 构建请求参数（对应pushdeer的要求）
    params = {
        "pushkey": PUSH_PLUS_TOKEN,
        "text": title,  # pushdeer的标题参数
        "desp": content  # pushdeer的内容参数（支持Markdown格式）
    }
    
    try:
        # 发送GET请求（pushdeer API要求GET方式）
        response = requests.get(
            url=request_url,
            params=params,
            timeout=10  # 增加超时控制，避免无限等待
        )
        
        # 处理响应
        if response.status_code == 200:
            json_res = response.json()
            # pushdeer返回格式：{"code":0,"msg":"success","content":...}
            if json_res.get("code") == 0:
                print(f"pushdeer推送成功：{json_res['msg']}")
            else:
                print(f"pushdeer推送失败：{json_res['code']}-{json_res['msg']}")
        else:
            print(f"pushdeer推送失败：HTTP状态码{response.status_code}")
    
    except requests.exceptions.Timeout:
        print("pushdeer推送超时")
    except requests.exceptions.ConnectionError:
        print("pushdeer推送连接错误")
    except Exception as e:
        print(f"pushdeer推送异常：{str(e)}")


class MiMotionRunner:
    def __init__(self, _user, _passwd):
        self.user_id = None
        self.device_id = str(uuid.uuid4())
        user = str(_user)
        password = str(_passwd)
        self.invalid = False
        self.log_str = ""
        if user == '' or password == '':
            self.error = "用户名或密码填写有误！"
            self.invalid = True
            pass
        self.password = password
        if (user.startswith("+86")) or "@" in user:
            user = user
        else:
            user = "+86" + user
        if user.startswith("+86"):
            self.is_phone = True
        else:
            self.is_phone = False
        self.user = user
        # self.fake_ip_addr = fake_ip()
        # self.log_str += f"创建虚拟ip地址：{self.fake_ip_addr}\n"

    # 登录
    def login(self):
        user_token_info = user_tokens.get(self.user)
        if user_token_info is not None:
            access_token = user_token_info.get("access_token")
            login_token = user_token_info.get("login_token")
            app_token = user_token_info.get("app_token")
            self.device_id = user_token_info.get("device_id")
            self.user_id = user_token_info.get("user_id")
            if self.device_id is None:
                self.device_id = str(uuid.uuid4())
                user_token_info["device_id"] = self.device_id
            ok,msg = zeppHelper.check_app_token(app_token)
            if ok:
                self.log_str += "使用加密保存的app_token\n"
                return app_token
            else:
                self.log_str += f"app_token失效 重新获取 last grant time: {user_token_info.get('app_token_time')}\n"
                # 检查login_token是否可用
                app_token, msg = zeppHelper.grant_app_token(login_token)
                if app_token is None:
                    self.log_str += f"login_token 失效 重新获取 last grant time: {user_token_info.get('login_token_time')}\n"
                    login_token, app_token, user_id, msg = zeppHelper.grant_login_tokens(access_token, self.device_id, self.is_phone)
                    if login_token is None:
                        self.log_str += f"access_token 已失效：{msg} last grant time:{user_token_info.get('access_token_time')}\n"
                    else:
                        user_token_info["login_token"] = login_token
                        user_token_info["app_token"] = app_token
                        user_token_info["user_id"] = user_id
                        user_token_info["login_token_time"] = get_time()
                        user_token_info["app_token_time"] = get_time()
                        self.user_id = user_id
                        return app_token
                else:
                    self.log_str += "重新获取app_token成功\n"
                    user_token_info["app_token"] = app_token
                    user_token_info["app_token_time"] = get_time()
                    return app_token

        # access_token 失效 或者没有保存加密数据
        access_token, msg = zeppHelper.login_access_token(self.user, self.password)
        if access_token is None:
            self.log_str += "登录获取accessToken失败：%s" % msg
            return None
        # print(f"device_id:{self.device_id} isPhone: {self.is_phone}")
        login_token, app_token, user_id, msg = zeppHelper.grant_login_tokens(access_token, self.device_id, self.is_phone)
        if login_token is None:
            self.log_str += f"登录提取的 access_token 无效：{msg}"
            return None

        user_token_info = dict()
        user_token_info["access_token"] = access_token
        user_token_info["login_token"] = login_token
        user_token_info["app_token"] = app_token
        user_token_info["user_id"] = user_id
        # 记录token获取时间
        user_token_info["access_token_time"] = get_time()
        user_token_info["login_token_time"] = get_time()
        user_token_info["app_token_time"] = get_time()
        if self.device_id is None:
            self.device_id = uuid.uuid4()
        user_token_info["device_id"] = self.device_id
        user_tokens[self.user] = user_token_info
        return app_token


    # 主函数
    def login_and_post_step(self, min_step, max_step):
        if self.invalid:
            return "账号或密码配置有误", False
        app_token = self.login()
        if app_token is None:
            return "登陆失败！", False

        step = str(random.randint(min_step, max_step))
        self.log_str += f"已设置为随机步数范围({min_step}~{max_step}) 随机值:{step}\n"
        ok, msg = zeppHelper.post_fake_brand_data(step, app_token, self.user_id)
        return f"修改步数（{step}）[" + msg + "]", ok


# 启动主函数
def push_to_push_plus(exec_results, summary):
    # 判断是否需要推送（保持原逻辑不变）
    if PUSH_PLUS_TOKEN is not None and PUSH_PLUS_TOKEN != '' and PUSH_PLUS_TOKEN != 'NO':
        if PUSH_PLUS_HOUR is not None and PUSH_PLUS_HOUR.isdigit():
            if time_bj.hour != int(PUSH_PLUS_HOUR):
                print(f"当前设置push_plus推送整点为：{PUSH_PLUS_HOUR}, 当前整点为：{time_bj.hour}，跳过推送")
                return
        
        # 构建纯文本+Markdown格式内容（去掉所有HTML标签）
        content = f"{summary}\n\n"  # 摘要先展示，换行分隔
        
        if len(exec_results) >= PUSH_PLUS_MAX:
            # 账号过多时的提示（纯文本）
            content += "⚠️ 账号数量过多，详细情况请前往github actions中查看"
        else:
            # 用Markdown列表展示每个账号的结果（清晰易读）
            content += "### 详细执行结果\n"
            for exec_result in exec_results:
                success = exec_result['success']
                user = exec_result["user"]
                msg = exec_result["msg"]
                if success is not None and success is True:
                    # 成功：绿色对勾标识
                    content += f"- ✅ 账号【{user}】：刷步数成功\n  接口返回：{msg}\n"
                else:
                    # 失败：红色叉号标识
                    content += f"- ❌ 账号【{user}】：刷步数失败\n  失败原因：{msg}\n"
        
        # 调用推送函数（保持原调用方式不变）
        push_plus(f"🏃🏻🏃🏻‍♀️🏃🏻‍♂️ {format_now()} 步数", content)


def run_single_account(total, idx, user_mi, passwd_mi):
    idx_info = ""
    if idx is not None:
        idx_info = f"[{idx + 1}/{total}]"
    log_str = f"[{format_now()}]\n{idx_info}账号：{desensitize_user_name(user_mi)}\n"
    try:
        runner = MiMotionRunner(user_mi, passwd_mi)
        min_step, max_step = get_min_max_by_time(user_mi, config)
        exec_msg, success = runner.login_and_post_step(min_step, max_step)
        log_str += runner.log_str
        log_str += f'{exec_msg}\n'
        exec_result = {"user": user_mi, "success": success,
                       "msg": exec_msg}
    except:
        log_str += f"执行异常:{traceback.format_exc()}\n"
        log_str += traceback.format_exc()
        exec_result = {"user": user_mi, "success": False,
                       "msg": f"执行异常:{traceback.format_exc()}"}
    print(log_str)
    return exec_result


def execute():
    user_list = users.split('#')
    passwd_list = passwords.split('#')
    exec_results = []
    if len(user_list) == len(passwd_list):
        idx, total = 0, len(user_list)
        if use_concurrent:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                exec_results = executor.map(lambda x: run_single_account(total, x[0], *x[1]),
                                            enumerate(zip(user_list, passwd_list)))
        else:
            for user_mi, passwd_mi in zip(user_list, passwd_list):
                exec_results.append(run_single_account(total, idx, user_mi, passwd_mi))
                idx += 1
                if idx < total:
                    # 每个账号之间间隔一定时间请求一次，避免接口请求过于频繁导致异常
                    time.sleep(sleep_seconds)
        if encrypt_support:
            persist_user_tokens()
        success_count = 0
        push_results = []
        for result in exec_results:
            push_results.append(result)
            if result['success'] is True:
                success_count += 1
        summary = f"\n执行账号总数{total}，成功：{success_count}，失败：{total - success_count}"
        print(summary)
        push_to_push_plus(push_results, summary)
    else:
        print(f"账号数长度[{len(user_list)}]和密码数长度[{len(passwd_list)}]不匹配，跳过执行")
        exit(1)


def prepare_user_tokens() -> dict:
    data_path = r"encrypted_tokens.data"
    if os.path.exists(data_path):
        with open(data_path, 'rb') as f:
            data = f.read()
        try:
            decrypted_data = decrypt_data(data, aes_key, None)
            # 假设原始明文为 UTF-8 编码文本
            return json.loads(decrypted_data.decode('utf-8', errors='strict'))
        except:
            print("密钥不正确或者加密内容损坏 放弃token")
            return dict()
    else:
        return dict()

def persist_user_tokens():
    data_path = r"encrypted_tokens.data"
    origin_str = json.dumps(user_tokens, ensure_ascii=False)
    cipher_data = encrypt_data(origin_str.encode("utf-8"), aes_key, None)
    with open(data_path, 'wb') as f:
        f.write(cipher_data)
        f.flush()
        f.close()

if __name__ == "__main__":
    # 北京时间
    time_bj = get_beijing_time()
    encrypt_support = False
    user_tokens = dict()
    if os.environ.__contains__("AES_KEY") is True:
        aes_key = os.environ.get("AES_KEY")
        if aes_key is not None:
            aes_key = aes_key.encode('utf-8')
            if len(aes_key) == 16:
                encrypt_support = True
        if encrypt_support:
            user_tokens = prepare_user_tokens()
        else:
            print("AES_KEY未设置或者无效 无法使用加密保存功能")
    if os.environ.__contains__("CONFIG") is False:
        print("未配置CONFIG变量，无法执行")
        exit(1)
    else:
        # region 初始化参数
        config = dict()
        try:
            config = dict(json.loads(os.environ.get("CONFIG")))
        except:
            print("CONFIG格式不正确，请检查Secret配置，请严格按照JSON格式：使用双引号包裹字段和值，逗号不能多也不能少")
            traceback.print_exc()
            exit(1)
        PUSH_PLUS_TOKEN = config.get('PUSH_PLUS_TOKEN')
        PUSH_PLUS_HOUR = config.get('PUSH_PLUS_HOUR')
        PUSH_PLUS_MAX = get_int_value_default('00000000', config, 'PUSH_PLUS_MAX', 30)
        sleep_seconds = config.get('SLEEP_GAP')
        if sleep_seconds is None or sleep_seconds == '':
            sleep_seconds = 5
        sleep_seconds = float(sleep_seconds)
        users = config.get('USER')
        passwords = config.get('PWD')
        if users is None or passwords is None:
            print("未正确配置账号密码，无法执行")
            exit(1)
        use_concurrent = config.get('USE_CONCURRENT')
        if use_concurrent is not None and use_concurrent == 'True':
            use_concurrent = True
        else:
            print(f"多账号执行间隔：{sleep_seconds}")
            use_concurrent = False
        # endregion
        execute()
