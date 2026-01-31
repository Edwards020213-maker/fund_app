import streamlit as st
import pandas as pd
import requests
import akshare as ak
import datetime
import time
import math
import json
import extra_streamlit_components as stx

# ==========================================
# 🔐 商家后台配置区
# ==========================================
VALID_VIP_CODES = [
    "LIHWQY","GO75ON","DXPIOA","SAMRUO","SGUGKB","K88CTV","I354RX", "K9IJMS","4ZF59V","27DP9A","U0CALN","1XVK1D","G6AW46","Q9TXDU","HH4FDG",
    "LGYUB6", "2S55MK","82GJKA","7RI4IN","YE9SEZ","VLBGKG","4VKIWT","Q7SL9J","6QEBLO","P1OHJR","59L0A3","L1OTDE","8LH0D3","BMTQSN","F7NKNF",
    "0MJ0RD","TFLKK3","AKBODE","SC87DP","G3WJAG","N3XX4X","AN09RU", "I1A2Z3", "RH1C5B", "Y6RMG9", "ZH3G5O", "GTCAPG", "PZE1LX", "WT7Z8O", "EO6LXU", 
    "BYK569", "84IDLA","ETCTZG","P6YI7G","QZGDLB"
]

UNLOCK_HINT = "请输入您的专属 VIP 兑换码"
BUY_GUIDE = "如需获取，请在购买平台（闲鱼/小红书）私信联系发货"
# ==========================================

# --- 0. 核心配置 ---
PROXY_MAP = {
    "黄金": "518880", "上海金": "518600", "豆粕": "159985",
    "有色": "512400", "化工": "516020", "石化": "516020",
    "石油": "561360", "油气": "513350", "煤炭": "515220",
    "沪深300": "510300", "上证50": "510050", "中证500": "510500",
    "科创50": "588000", "创业板": "159915", "微盘": "563300",
    "半导体": "512480", "芯片": "159995", "人工智能": "159819",
    "游戏": "159869", "传媒": "512980", "光伏": "515790",
    "新能源": "515030", "白酒": "161725", "医疗": "512170",
    "医药": "512010", "证券": "512000", "银行": "512800",
    "纳斯达克": "513100", "纳指": "513100", "标普500": "513500",
    "恒生科技": "513180", "恒生互联网": "513330", "中概互联": "513050",
    "恒生指数": "159920", "日经": "513520", "港股通互联网": "159792",
}

# --- 1. 基础工具函数 ---
def get_tencent_code(symbol):
    s = str(symbol).strip().upper()
    if s.isalpha(): return f"us{s}"
    if len(s) == 5 and s.isdigit(): return f"hk{s}"
    if len(s) == 6 and s.isdigit():
        if s.startswith(('5','6','9')): return f"sh{s}"
        if s.startswith(('0','1','2','3')): return f"sz{s}"
    return None

def fetch_quotes_universal(code_list):
    if not code_list: return {}, 0.0
    unique_codes = list(set(code_list))
    t_codes = []
    map_ref = {}
    need_fx = False
    
    for c in unique_codes:
        tc = get_tencent_code(c)
        if tc:
            key = f"s_{tc}"
            t_codes.append(key)
            map_ref[key] = c
            if "us" in tc: need_fx = True
    
    if need_fx: t_codes.append("s_usUSDCNH")
    
    res_dict = {}
    fx_change = 0.0
    
    try:
        rand_param = int(time.time() * 1000)
        url = f"http://qt.gtimg.cn/q={','.join(t_codes)}&_={rand_param}"
        r = requests.get(url, timeout=3)
        r.encoding = 'gbk'
        for line in r.text.split(';'):
            if '=' not in line: continue
            k, v = line.split('=', 1)
            data = v.strip('"').split('~')
            if len(data) < 6: continue
            
            if "s_usUSDCNH" in k:
                try: fx_change = float(data[5])
                except: pass
            else:
                key_clean = k.split('v_')[-1]
                raw = map_ref.get(key_clean)
                if raw:
                    try: res_dict[raw] = float(data[5])
                    except: pass
    except: pass
    return res_dict, fx_change

def get_fund_name_only(fund_code):
    try:
        ts = int(time.time() * 1000)
        url = f"http://qt.gtimg.cn/q=jj{fund_code}&t={ts}"
        r = requests.get(url, timeout=2)
        r.encoding = 'gbk'
        if '="' in r.text:
            data = r.text.split('="')[1].split('~')
            if len(data) > 1:
                return data[1]
    except: pass
    return f"基金{fund_code}"

# --- 2. 核心分析逻辑 ---
def analyze_fund_profit_by_amount(fund_code, holding_amount):
    fund_name = get_fund_name_only(fund_code)
    est_change = 0.0
    method = "❌ 未知"
    detail = "无数据"
    
    if "债" in fund_name and "可转债" not in fund_name:
        est_change = 0.0
        method = "🛡️ 债券基金"
        detail = "忽略波动"
    
    elif not method.startswith("🛡️"):
        found_proxy = False
        for kw, proxy in PROXY_MAP.items():
            if kw in fund_name:
                q, _ = fetch_quotes_universal([proxy])
                est_change = q.get(proxy, 0.0)
                method = "⚡ 行业锚定"
                detail = f"追踪 {kw}({proxy})"
                found_proxy = True
                break
        
        if not found_proxy:
            holdings_df = pd.DataFrame()
            try:
                cur_year = datetime.datetime.now().year
                for y in [cur_year, cur_year-1]:
                    df = ak.fund_portfolio_hold_em(symbol=fund_code, date=str(y))
                    if not df.empty:
                        holdings_df = df[df['季度'] == df['季度'].max()].copy()
                        break
            except: pass
            
            if not holdings_df.empty:
                stocks = holdings_df['股票代码'].astype(str).tolist()
                weights = pd.to_numeric(holdings_df['占净值比例'], errors='coerce') / 100
                quotes, fx = fetch_quotes_universal(stocks)
                
                total_w = 0; total_c = 0; us_count = 0
                for i, s in enumerate(stocks):
                    if s in quotes:
                        w = weights.iloc[i]
                        c = quotes[s]
                        if s.isalpha(): c += fx; us_count += 1
                        total_c += w * c; total_w += w
                        
                if total_w > 0.05:
                    est_change = total_c / total_w
                    if us_count > 3: method = "🇺🇸 美股穿透"; detail = f"昨收+汇率({fx:+.2f}%)"
                    else: method = "📈 持仓穿透"; detail = f"基于 {len(stocks)} 只持仓"
    
    try:
        safe_amount = float(holding_amount)
        if math.isnan(safe_amount): safe_amount = 0.0
    except:
        safe_amount = 0.0
        
    profit = safe_amount * (est_change / 100)
    
    return {"code": fund_code, "name": fund_name, "change_pct": est_change, "profit": profit, "amount": safe_amount, "method": method, "detail": detail}

# --- 3. Streamlit 界面 ---
st.set_page_config(page_title="基金估值Pro", page_icon="💰", layout="wide")

# ================= 🍪 Cookie 管理器 (修复版) =================
# key="cookie_manager" 确保每次重运行ID一致，避免组件闪烁
cookie_manager = stx.CookieManager(key="cookie_mgr")

# 1. 尝试获取 Cookie
cookie_data_json = cookie_manager.get("my_fund_portfolio_v20")
vip_status = cookie_manager.get("vip_status")

# 2. 默认数据定义
DEFAULT_DATA = [
    {"代码": "013403", "持仓金额": 10000.50, "备注": "演示持仓"},
    {"代码": "005827", "持仓金额": 0.00, "备注": "演示观察"},
]

# 3. 初始化 Session State
if "fund_data" not in st.session_state:
    st.session_state.fund_data = pd.DataFrame(DEFAULT_DATA)

# 4. [核心修复] 自动同步逻辑
# 如果 Cookie 有数据，且我们还没标记“已同步”，则强制加载一次
if cookie_data_json and "data_synced" not in st.session_state:
    try:
        st.session_state.fund_data = pd.DataFrame(json.loads(cookie_data_json))
        st.session_state.data_synced = True # 标记为已同步
        st.rerun() # 强制刷新页面显示新数据
    except:
        pass

# 5. VIP 状态自动加载
if "vip_unlocked" not in st.session_state:
    st.session_state.vip_unlocked = True if vip_status == "unlocked" else False

st.markdown("### 💰 基金实盘估值 V20.0")
st.caption("全能版：支持股票/ETF/QDII | 🚀 输入本金，一键计算今日盈亏")

with st.expander("📝 编辑持仓 (支持粘贴Excel)", expanded=True):
    col_a, col_b = st.columns([3, 1])
    
    # 增加手动读取按钮，防止自动同步失败
    with col_b:
        if st.button("📥 读取云端存档", help="如果刷新后数据消失，请点我"):
            c_data = cookie_manager.get("my_fund_portfolio_v20")
            if c_data:
                st.session_state.fund_data = pd.DataFrame(json.loads(c_data))
                st.session_state.data_synced = True
                st.rerun()
            else:
                st.warning("暂无存档记录")
        
        if st.button("🗑️ 清空表格"):
            st.session_state.fund_data = pd.DataFrame([{"代码": "", "持仓金额": 0.00, "备注": ""}])
            st.rerun()

    edited_df = st.data_editor(
        st.session_state.fund_data,
        num_rows="dynamic",
        column_config={
            "代码": st.column_config.TextColumn(help="6位代码"),
            "持仓金额": st.column_config.NumberColumn(
                min_value=0.0, 
                format="%.2f", 
                step=0.01, 
                help="输入本金 (支持两位小数)"
            ),
            "备注": st.column_config.TextColumn(),
        },
        use_container_width=True
    )
    
    # 保存按钮
    if st.button("💾 保存当前配置 (下次自动加载)", use_container_width=True):
        json_str = edited_df.to_json(orient="records")
        # 写入 Cookie，有效期 30 天
        cookie_manager.set("my_fund_portfolio_v20", json_str, expires_at=datetime.datetime.now() + datetime.timedelta(days=30))
        st.toast("✅ 配置已保存！刷新页面也不会丢失了。", icon="💾")
        # 同时标记已同步，防止保存后立刻被旧逻辑覆盖
        st.session_state.data_synced = True 

start_calc = st.button("🚀 开始估值", type="primary", use_container_width=True)

if start_calc or st.session_state.get('show_results', False):
    st.session_state.show_results = True
    
    mask_has_code = edited_df["代码"].astype(str).str.strip() != ""
    valid_rows = edited_df[mask_has_code].copy()
    valid_rows["持仓金额"] = pd.to_numeric(valid_rows["持仓金额"], errors='coerce').fillna(0.0)
    
    if valid_rows.empty:
        st.warning("请至少输入一行基金代码")
        st.stop()

    if not st.session_state.vip_unlocked:
        st.divider()
        with st.container():
            st.warning("🔒 正在计算收益... (高级功能已锁定)")
            c1, c2 = st.columns([3, 1])
            with c1:
                pwd_input = st.text_input(UNLOCK_HINT, key="pwd_try", placeholder="请输入闲鱼/小红书获取的卡密").strip()
            with c2:
                st.write("") 
                st.write("") 
                if st.button("🔓 立即验证"):
                    if pwd_input in VALID_VIP_CODES:
                        st.session_state.vip_unlocked = True
                        cookie_manager.set("vip_status", "unlocked", expires_at=datetime.datetime.now() + datetime.timedelta(days=30))
                        st.success("✅ 验证成功！欢迎尊贵的 Pro 会员")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("❌ 无效的兑换码")
            st.caption(f"💡 {BUY_GUIDE}")
        
        st.markdown("---")
        st.subheader("📊 基础涨跌幅 (预览模式)")
        for index, row in valid_rows.iterrows():
            code = str(row["代码"]).strip()
            res = analyze_fund_profit_by_amount(code, 0.0)
            val = res['change_pct']; icon = "🔴" if val > 0 else "🟢"
            with st.container():
                c1, c2 = st.columns([2, 1])
                with c1:
                    st.markdown(f"**{res['name']}**")
                    st.caption(f"{res['code']} | {res['method']}")
                with c2:
                    st.markdown(f"**{icon} {val:+.2f}%**")
                    st.caption("🔒 收益隐藏")
                st.divider()

    else:
        results = []
        progress_bar = st.progress(0)
        total_profit = 0.0; total_principal = 0.0
        
        for index, row in valid_rows.iterrows():
            code = str(row["代码"]).strip()
            amount = float(row["持仓金额"])
            res = analyze_fund_profit_by_amount(code, amount)
            res['user_remark'] = row.get("备注", "")
            results.append(res)
            
            safe_profit = res['profit'] if not math.isnan(res['profit']) else 0.0
            total_profit += safe_profit
            total_principal += amount
            progress_bar.progress((index + 1) / len(valid_rows))
            
        progress_bar.empty()
        
        st.markdown("---")
        if math.isnan(total_profit): total_profit = 0.0
        bg_color = "#ffebee" if total_profit > 0 else "#e8f5e9"
        border_color = "red" if total_profit > 0 else "green"
        sign = "+" if total_profit > 0 else ""
        
        st.markdown(
            f"""
            <div style="background-color:{bg_color}; padding:15px; border-radius:10px; border-left: 5px solid {border_color}; text-align:center;">
                <h4 style="margin:0; color:#666;">今日预估总盈亏 (Pro)</h4>
                <h2 style="margin:5px 0; color:{border_color};">{sign}{total_profit:,.2f} 元</h2>
                <small>持仓本金: {total_principal:,.2f} 元</small>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown("### 📋 详细数据")
        for res in results:
            val = res['change_pct']; profit = res['profit']; amount = res['amount']
            color = "gray"; icon = "⚪"
            if val > 0: color = "red"; icon = "🔴"
            elif val < 0: color = "green"; icon = "🟢"
            display_profit = profit if not math.isnan(profit) else 0.0
            
            with st.container():
                c1, c2 = st.columns([1.5, 1])
                with c1:
                    st.markdown(f"**{res['name']}**")
                    st.caption(f"{res['code']} | {res['method']}")
                    if res['user_remark']: st.caption(f"备注: {res['user_remark']}")
                with c2:
                    st.markdown(f"**{icon} {val:+.2f}%**")
                    if amount > 0:
                        p_sign = "+" if display_profit > 0 else ""
                        st.markdown(f":{color}[**{p_sign}{display_profit:.2f} 元**]")
                    else: st.caption("👀 观察中")
                st.text(res['detail'])
                st.divider()
