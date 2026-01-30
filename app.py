import streamlit as st
import pandas as pd
import requests
import akshare as ak
import datetime
import os

# --- 核心逻辑配置 (直接复用 V7.0) ---
PROXY_MAP = {
    # ... (保持原本 V7.0 的 PROXY_MAP 字典内容，为了篇幅这里省略，请务必完整复制进来) ...
    # === 大宗商品/贵金属 ===
    "黄金": "518880", "上海金": "518600", "豆粕": "159985",
    "有色": "512400", "化工": "516020", "石化": "516020",
    "石油": "561360", "油气": "513350", "煤炭": "515220",
    # === 宽基 ===
    "沪深300": "510300", "上证50": "510050", "中证500": "510500",
    "科创50": "588000", "创业板": "159915", "微盘": "563300",
    # === 行业 ===
    "半导体": "512480", "芯片": "159995", "人工智能": "159819",
    "游戏": "159869", "传媒": "512980", "光伏": "515790",
    "新能源": "515030", "白酒": "161725", "医疗": "512170",
    "医药": "512010", "证券": "512000", "银行": "512800",
    # === 跨境 ===
    "纳斯达克": "513100", "纳指": "513100", "标普500": "513500",
    "恒生科技": "513180", "恒生互联网": "513330", "中概互联": "513050",
    "恒生指数": "159920", "日经": "513520",
}

# --- 工具函数 (复用 V7.0) ---
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
    
    # 简单请求
    try:
        url = f"http://qt.gtimg.cn/q={','.join(t_codes)}"
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

def get_fund_info_tencent(fund_code):
    try:
        url = f"http://qt.gtimg.cn/q=jj{fund_code}"
        r = requests.get(url, timeout=2)
        r.encoding = 'gbk'
        text = r.text
        if '="' in text:
            return text.split('="')[1].strip('";').split('~')[1]
    except: pass
    return f"基金{fund_code}"

# --- 分析逻辑 (改造为适配 Streamlit) ---
def analyze_fund(fund_code):
    # 1. 拿名字
    fund_name = get_fund_info_tencent(fund_code)
    
    # 2. 债券判断
    if "债" in fund_name and "可转债" not in fund_name:
        return {"name": fund_name, "val": 0.0, "method": "🛡️ 债券基金", "detail": "波动极小"}
        
    # 3. 代理映射
    for kw, proxy in PROXY_MAP.items():
        if kw in fund_name:
            q, _ = fetch_quotes_universal([proxy])
            return {"name": fund_name, "val": q.get(proxy, 0.0), "method": "⚡ 行业锚定", "detail": f"追踪 {kw}({proxy})"}
            
    # 4. 查持仓
    holdings_df = pd.DataFrame()
    try:
        cur_year = datetime.datetime.now().year
        for y in [cur_year, cur_year-1]:
            df = ak.fund_portfolio_hold_em(symbol=fund_code, date=str(y))
            if not df.empty:
                holdings_df = df[df['季度'] == df['季度'].max()].copy()
                break
    except: pass
    
    # 5. 计算
    if not holdings_df.empty:
        stocks = holdings_df['股票代码'].astype(str).tolist()
        weights = pd.to_numeric(holdings_df['占净值比例'], errors='coerce') / 100
        quotes, fx = fetch_quotes_universal(stocks)
        
        total_w = 0
        total_c = 0
        us_count = 0
        for i, s in enumerate(stocks):
            if s in quotes:
                w = weights.iloc[i]
                c = quotes[s]
                if s.isalpha(): 
                    c += fx
                    us_count += 1
                total_c += w * c
                total_w += w
                
        if total_w > 0.05:
            est = total_c / total_w
            if us_count > 3:
                return {"name": fund_name, "val": est, "method": "🇺🇸 美股穿透", "detail": f"昨收+汇率({fx:+.2f}%)"}
            else:
                return {"name": fund_name, "val": est, "method": "📈 持仓穿透", "detail": f"基于 {len(stocks)} 只持仓"}

    return {"name": fund_name, "val": 0.0, "method": "❌ 无法估算", "detail": "无数据"}

# --- Streamlit 界面代码 ---

st.set_page_config(page_title="基金估值助手", page_icon="📈")

st.title("📈 基金盘中实时估值 V7.0")
st.markdown("支持：**股票型 / ETF联接 / QDII / 黄金 / 行业指数**")

# 输入框
default_codes = "013403, 005827, 000834, 000217, 007911"
user_input = st.text_input("请输入基金代码 (逗号分隔):", value=default_codes)

if st.button("开始估值", type="primary"):
    codes = [c.strip() for c in user_input.replace("，", ",").split(",") if c.strip()]
    
    if not codes:
        st.warning("请输入有效的代码")
    else:
        # 创建一个进度条
        progress_bar = st.progress(0)
        results = []
        
        for i, code in enumerate(codes):
            res = analyze_fund(code)
            results.append({
                "代码": code,
                "名称": res['name'].replace("发起式","").replace("联接","").replace("人民币","")[:10],
                "估值": res['val'],
                "模式": res['method'],
                "详情": res['detail']
            })
            progress_bar.progress((i + 1) / len(codes))
            
        progress_bar.empty() # 清除进度条
        
        # 展示结果
        st.subheader("📊 估值结果")
        
        # 将结果转换为 DataFrame 以便美化展示
        for row in results:
            val = row['估值']
            color = "gray"
            if val > 0: color = "red"
            elif val < 0: color = "green"
            
            # 使用卡片式布局展示
            col1, col2, col3 = st.columns([2, 1, 2])
            with col1:
                st.markdown(f"**{row['名称']}** ({row['代码']})")
                st.caption(row['模式'])
            with col2:
                st.markdown(f":{color}[**{val:+.2f}%**]")
            with col3:
                st.text(row['详情'])
            st.divider()