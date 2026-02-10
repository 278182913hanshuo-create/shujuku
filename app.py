import streamlit as st
import pandas as pd
import requests
import json
from datetime import datetime
import time

# --- 页面配置 ---
st.set_page_config(
    page_title="供应商设备价格数据库 (飞书版)",
    page_icon="🐼",
    layout="wide"
)

# --- 登录验证功能 ---
def check_login():
    """简单的登录验证"""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("🔐 系统登录")
        with st.form("login_form"):
            username = st.text_input("账号")
            password = st.text_input("密码", type="password")
            submitted = st.form_submit_button("登录")

            if submitted:
                # 默认密码 admin / 123456
                valid_users = st.secrets.get("credentials", {"admin": "123456"})
                if username in valid_users and valid_users[username] == password:
                    st.session_state.authenticated = True
                    st.success("登录成功！")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("账号或密码错误。")
    return False

# --- 飞书 API 工具类 ---
class FeishuConnector:
    def __init__(self):
        if "feishu" not in st.secrets:
            st.error("未找到飞书配置！请在 Secrets 中配置。")
            st.stop()
        
        self.app_id = st.secrets["feishu"]["app_id"]
        self.app_secret = st.secrets["feishu"]["app_secret"]
        self.app_token = st.secrets["feishu"]["app_token"]
        self.table_id = st.secrets["feishu"]["table_id"]
        self.token_url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        self.base_url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records"

    def get_token(self):
        headers = {"Content-Type": "application/json; charset=utf-8"}
        data = {"app_id": self.app_id, "app_secret": self.app_secret}
        try:
            response = requests.post(self.token_url, headers=headers, json=data)
            return response.json().get("tenant_access_token")
        except:
            return None

    def get_records(self):
        token = self.get_token()
        if not token: return []
        
        headers = {"Authorization": f"Bearer {token}"}
        # page_size 可根据需要调整，最大 500
        params = {"page_size": 100} 
        
        try:
            response = requests.get(self.base_url, headers=headers, params=params)
            res_json = response.json()
            if res_json.get("code") == 0:
                items = res_json["data"]["items"]
                clean_data = []
                for item in items:
                    row = item["fields"]
                    row["_record_id"] = item["record_id"]
                    clean_data.append(row)
                return clean_data
            else:
                st.error(f"读取数据失败: {res_json.get('msg')}")
                return []
        except Exception as e:
            st.error(f"请求错误: {e}")
            return []

    def add_record(self, data_dict):
        token = self.get_token()
        if not token: return False
        
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
        payload = {"fields": data_dict}
        response = requests.post(self.base_url, headers=headers, json=payload)
        return response.json().get("code") == 0

    def delete_record(self, record_id):
        token = self.get_token()
        if not token: return False
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.delete(f"{self.base_url}/{record_id}", headers=headers)
        return response.json().get("code") == 0

# ==========================================
#  主程序逻辑
# ==========================================

if check_login():
    connector = FeishuConnector()

    st.sidebar.title("🐼 飞书云数据库")
    
    # --- 调试工具 ---
    with st.sidebar.expander("🔧 调试模式 (列名检查)"):
        st.write("如果数据没显示，请检查飞书列名是否与代码一致。")
        show_debug = st.checkbox("显示原始列名")

    if st.sidebar.button("🚪 退出登录"):
        st.session_state.authenticated = False
        st.rerun()
        
    menu = st.sidebar.radio("功能菜单", ["📊 数据查询", "➕ 录入报价", "📈 价格分析"])

    # --- 功能 1: 数据查询 ---
    if menu == "📊 数据查询":
        st.title("📊 供应商采购成本数据库")
        
        with st.spinner("正在连接飞书服务器..."):
            data = connector.get_records()
        
        if data:
            df = pd.DataFrame(data)
            
            # --- 兼容性处理：如果旧数据叫"单价"，新数据叫"询价单价"，统一改名方便查看 ---
            if "单价" in df.columns and "询价单价" not in df.columns:
                df.rename(columns={"单价": "询价单价"}, inplace=True)

            # --- 调试显示 ---
            if show_debug:
                st.info(f"飞书返回的实际列名: {list(df.columns)}")
                st.write("请确保飞书里的列名包含：供应商、联系人、设备类型、询价单价、录入时间、备注")

            # 定义想要显示的列顺序
            target_cols = ["供应商", "联系人", "设备类型", "询价单价", "录入时间", "备注"]
            
            # 过滤出实际存在的列，防止报错
            display_cols = [c for c in target_cols if c in df.columns]
            
            # 始终保留 _record_id 用于删除操作，但不显示
            final_df = df.copy()

            # --- 搜索框 ---
            search_q = st.text_input("🔍 全局搜索 (供应商/联系人/设备)", placeholder="输入关键字...")
            if search_q:
                mask = final_df.astype(str).apply(lambda x: x.str.contains(search_q, case=False)).any(axis=1)
                final_df = final_df[mask]

            # --- 显示数据表格 ---
            st.write(f"共找到 {len(final_df)} 条记录")
            st.dataframe(
                final_df[display_cols], # 只显示指定的列
                use_container_width=True,
                hide_index=True,
                column_config={
                    "询价单价": st.column_config.NumberColumn(format="¥ %.2f"),
                    "录入时间": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm"),
                }
            )

            # --- 删除功能 ---
            with st.expander("🗑️ 删除记录"):
                if not final_df.empty:
                    # 制作一个下拉菜单的选项列表
                    records_to_delete = final_df.to_dict('records')
                    
                    def fmt_func(row):
                        # 下拉框里显示的文字格式
                        sup = row.get("供应商", "未知供应商")
                        dev = row.get("设备类型", "未知设备")
                        price = row.get("询价单价", 0)
                        return f"{sup} - {dev} (¥{price})"

                    selected_row = st.selectbox("选择要删除的行", records_to_delete, format_func=fmt_func)
                    
                    if st.button("确认删除"):
                        if connector.delete_record(selected_row["_record_id"]):
                            st.success("删除成功！")
                            time.sleep(1)
                            st.rerun()

        else:
            st.info("表格为空，或连接失败。请先去【录入报价】页面添加数据。")

    # --- 功能 2: 录入报价 ---
    elif menu == "➕ 录入报价":
        st.title("➕ 录入新报价")
        st.caption("请确保飞书表格中已包含以下列名，否则可能写入失败。")
        
        with st.form("new_entry"):
            c1, c2 = st.columns(2)
            with c1:
                supplier = st.text_input("供应商", placeholder="xx科技有限公司")
                contact = st.text_input("联系人", placeholder="王经理 138...")
                device = st.text_input("设备类型", placeholder="例如：离心泵")
            with c2:
                price = st.number_input("询价单价 (¥)", min_value=0.0, step=100.0)
                # 可选：如果你还需要其他字段，可以在这里加，但在“查询”页我默认隐藏了它们
                note = st.text_area("备注", placeholder="含税/交货期/参数等")
            
            submitted = st.form_submit_button("🚀 提交")

            if submitted:
                if not supplier:
                    st.warning("请填写供应商名称")
                else:
                    # 构建数据字典 (Key 必须与飞书列名完全一致)
                    payload = {
                        "供应商": supplier,
                        "联系人": contact,
                        "设备类型": device,
                        "询价单价": price,  # 注意：这里改成了“询价单价”
                        "备注": note,
                        "录入时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    
                    # 清除空值
                    clean_payload = {k: v for k, v in payload.items() if v}
                    
                    if connector.add_record(clean_payload):
                        st.success(f"✅ 已录入：{supplier} - {device}")
                        time.sleep(1)
                        # 自动刷新页面重置表单
                        st.rerun()

    # --- 功能 3: 价格分析 ---
    elif menu == "📈 价格分析":
        st.title("📈 简易分析")
        data = connector.get_records()
        if data:
            df = pd.DataFrame(data)
            # 兼容改名
            if "单价" in df.columns and "询价单价" not in df.columns:
                df.rename(columns={"单价": "询价单价"}, inplace=True)

            if not df.empty and "询价单价" in df.columns:
                tab1, tab2 = st.tabs(["按供应商", "按设备类型"])
                
                with tab1:
                    if "供应商" in df.columns:
                        avg_price = df.groupby("供应商")["询价单价"].mean()
                        st.bar_chart(avg_price)
                        st.caption("各供应商平均报价")
                
                with tab2:
                    if "设备类型" in df.columns:
                        dev_price = df.groupby("设备类型")["询价单价"].mean()
                        st.bar_chart(dev_price)
                        st.caption("各设备类型平均报价")
            else:
                st.info("暂无足够数据生成图表 (需要包含'询价单价'列)")
        else:
            st.info("暂无数据")
