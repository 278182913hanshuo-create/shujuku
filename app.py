import streamlit as st
import pandas as pd
import requests
import json
from datetime import datetime
import time

# --- 页面配置 ---
st.set_page_config(
    page_title="北京富达采购成本数据库",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 样式还原 ---
hide_streamlit_style = """
<style>
    footer { visibility: hidden; }
    .stDeployButton { display: none; }
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# --- 登录验证功能 ---
def check_login():
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
                valid_users = st.secrets.get("credentials", {"admin": "123456"})
                if username in valid_users and valid_users[username] == password:
                    st.session_state.authenticated = True
                    st.success("登录成功！")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("账号或密码错误。")
    return False

# --- 飞书 API 工具类 (已升级支持多表) ---
class FeishuConnector:
    def __init__(self):
        if "feishu" not in st.secrets:
            st.error("未找到飞书配置！请在 Secrets 中配置。")
            st.stop()
        
        self.app_id = st.secrets["feishu"]["app_id"]
        self.app_secret = st.secrets["feishu"]["app_secret"]
        self.app_token = st.secrets["feishu"]["app_token"]
        # 主表（用于报价和查询）
        self.table_id = st.secrets["feishu"]["table_id"]
        # 考核表（独立分开存放）
        self.assessment_table_id = st.secrets["feishu"].get("assessment_table_id", None)
        
        self.token_url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        self.base_url_template = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{self.app_token}/tables/{{}}/records"

    def get_token(self):
        headers = {"Content-Type": "application/json; charset=utf-8"}
        data = {"app_id": self.app_id, "app_secret": self.app_secret}
        try:
            response = requests.post(self.token_url, headers=headers, json=data)
            return response.json().get("tenant_access_token")
        except:
            return None

    def get_records(self, table_id):
        """获取指定表的数据"""
        token = self.get_token()
        if not token or not table_id: return []
        
        url = self.base_url_template.format(table_id)
        headers = {"Authorization": f"Bearer {token}"}
        params = {"page_size": 100} 
        
        try:
            response = requests.get(url, headers=headers, params=params)
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
                return []
        except Exception as e:
            return []

    def add_record(self, table_id, data_dict):
        """向指定表新增记录"""
        token = self.get_token()
        if not token or not table_id: return False
        
        url = self.base_url_template.format(table_id)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
        payload = {"fields": data_dict}
        
        try:
            response = requests.post(url, headers=headers, json=payload)
            res_json = response.json()
            if res_json.get("code") == 0:
                return True
            else:
                st.error(f"❌ 提交失败: {res_json.get('msg')}")
                return False
        except Exception:
            st.error("网络请求出错")
            return False

    def update_record(self, table_id, record_id, data_dict):
        """更新指定表的指定记录"""
        token = self.get_token()
        if not token or not table_id: return False
        
        url = f"{self.base_url_template.format(table_id)}/{record_id}"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
        payload = {"fields": data_dict}
        
        try:
            response = requests.put(url, headers=headers, json=payload)
            if response.json().get("code") == 0:
                return True
            return False
        except Exception:
            return False

    def delete_record(self, table_id, record_id):
        """删除指定表的记录"""
        token = self.get_token()
        if not token or not table_id: return False
        
        url = f"{self.base_url_template.format(table_id)}/{record_id}"
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.delete(url, headers=headers)
        return response.json().get("code") == 0

# ==========================================
#  主程序逻辑
# ==========================================

if check_login():
    connector = FeishuConnector()

    st.sidebar.title("北京富达采购数据库")
    
    if st.sidebar.button("🚪 退出登录"):
        st.session_state.authenticated = False
        st.rerun()
        
    menu = st.sidebar.radio("功能菜单", ["📊 数据查询", "➕ 录入报价", "📝 供应商考核"])

    # 获取报价表数据（主表）
    quote_records = connector.get_records(connector.table_id)
    quote_columns = list(pd.DataFrame(quote_records).columns) if quote_records else []
    if "_record_id" in quote_columns: quote_columns.remove("_record_id")

    # --- 功能 1: 数据查询 (纯净版，不再混杂考核数据) ---
    if menu == "📊 数据查询":
        st.title("📊 采购成本查询")
        
        if quote_records:
            df = pd.DataFrame(quote_records)
            
            if "单价" in df.columns and "询价单价" not in df.columns:
                df.rename(columns={"单价": "询价单价"}, inplace=True)

            target_cols = ["供应商", "联系人", "设备类型", "询价单价", "录入时间", "备注"]
            display_cols = [c for c in target_cols if c in df.columns]
            
            final_df = df.copy()

            search_q = st.text_input("🔍 全局搜索", placeholder="输入关键字...")
            if search_q:
                mask = final_df.astype(str).apply(lambda x: x.str.contains(search_q, case=False)).any(axis=1)
                final_df = final_df[mask]

            final_df = final_df.reset_index(drop=True)

            st.write(f"共找到 **{len(final_df)}** 条报价记录。💡 双击单元格可修改，完成后点击下方保存。")
            
            editor_data = final_df[display_cols] if display_cols else final_df
            
            st.data_editor(
                editor_data,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "询价单价": st.column_config.NumberColumn(format="¥ %.2f"),
                    "录入时间": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm", disabled=True),
                },
                key="db_editor"
            )

            # 保存修改
            if st.button("💾 保存表格修改", type="primary"):
                edits = st.session_state.get("db_editor", {}).get("edited_rows", {})
                if edits:
                    success_count = 0
                    with st.spinner("同步至飞书..."):
                        for idx_str, changes in edits.items():
                            idx = int(idx_str)
                            real_record_id = final_df.iloc[idx]["_record_id"]
                            payload = {}
                            for col, val in changes.items():
                                if col == "询价单价" and "单价" in quote_columns:
                                    payload["单价"] = val
                                else:
                                    payload[col] = val
                            
                            if payload and connector.update_record(connector.table_id, real_record_id, payload):
                                success_count += 1
                                    
                    if success_count > 0:
                        st.success(f"✅ 成功更新了 {success_count} 条记录！")
                        time.sleep(1)
                        st.rerun()

            # 删除记录
            with st.expander("🗑️ 删除记录"):
                if not final_df.empty:
                    selected_row = st.selectbox("选择要删除的行", final_df.to_dict('records'), format_func=lambda x: f"{x.get('供应商', '未知')} - {x.get('设备类型', '未知')}")
                    if st.button("确认删除"):
                        if connector.delete_record(connector.table_id, selected_row["_record_id"]):
                            st.success("删除成功！")
                            time.sleep(1)
                            st.rerun()
        else:
            st.info("主表格为空或连接失败。")

    # --- 功能 2: 录入报价 (存入主表) ---
    elif menu == "➕ 录入报价":
        st.title("➕ 录入新报价")
        with st.form("new_entry"):
            c1, c2 = st.columns(2)
            with c1:
                supplier = st.text_input("供应商", placeholder="xx科技有限公司")
                contact = st.text_input("联系人", placeholder="王经理 138...")
                device = st.text_input("设备类型", placeholder="例如：离心泵")
            with c2:
                price = st.number_input("询价单价 (¥)", min_value=0.0, step=100.0)
                note = st.text_area("备注", placeholder="含税/交货期/参数等")
            
            if st.form_submit_button("🚀 提交"):
                if not supplier:
                    st.warning("请填写供应商名称")
                else:
                    price_key = "单价" if "单价" in quote_columns else "询价单价"
                    payload = {"供应商": supplier, "联系人": contact, "设备类型": device, price_key: price, "备注": note, "录入时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
                    clean_payload = {k: v for k, v in payload.items() if v is not None and v != ""}
                    
                    if connector.add_record(connector.table_id, clean_payload):
                        st.success(f"✅ 已录入：{supplier} - {device}")
                        time.sleep(1)
                        st.rerun()

    # --- 功能 3: 供应商考核 (存入独立的考核表) ---
    elif menu == "📝 供应商考核":
        st.title("📝 供应商绩效考核")
        
        # 拦截检查：如果没有配置考核表的 ID，则给出提示
        if not connector.assessment_table_id:
            st.warning("⚠️ 检测到您还未配置独立的考核数据表！")
            st.info("请在系统的 Secrets 配置中添加 `assessment_table_id = '您飞书中考核表的真实ID'`。")
            st.stop()
            
        tab1, tab2 = st.tabs(["➕ 新建考核", "📜 历史考核记录"])
        
        with tab1:
            # 下拉列表的数据仍然从“报价主表”中提取供应商名字，方便用户选择
            supplier_list = []
            if quote_records:
                df_temp = pd.DataFrame(quote_records)
                if "供应商" in df_temp.columns:
                    supplier_list = df_temp["供应商"].dropna().unique().tolist()

            with st.form("assessment_form"):
                target_supplier = st.selectbox("选择被考核供应商", supplier_list) if supplier_list else st.text_input("被考核供应商名称")
                
                st.divider()
                col1, col2 = st.columns(2)
                with col1:
                    score_quality = st.slider("产品质量评分 (40%)", 0, 100, 80)
                    score_delivery = st.slider("交付及时性评分 (30%)", 0, 100, 80)
                with col2:
                    score_price = st.slider("价格竞争力评分 (20%)", 0, 100, 80)
                    score_service = st.slider("售后服务评分 (10%)", 0, 100, 80)
                
                comments = st.text_area("考核评语/改进建议")
                
                if st.form_submit_button("📤 提交考核结果"):
                    if not target_supplier:
                        st.warning("请填写供应商名称")
                    else:
                        avg_score = (score_quality + score_delivery + score_price + score_service) / 4
                        detail_note = f"质量:{score_quality} | 交付:{score_delivery} | 价格:{score_price} | 服务:{score_service} | 评语:{comments}"

                        # 将考核数据发送到独立的【考核表】
                        # 注意：请确保飞书的考核表中有这几个字段名称
                        payload = {
                            "供应商": target_supplier,
                            "总分": float(avg_score),
                            "考核详情": detail_note,
                            "录入时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        
                        if connector.add_record(connector.assessment_table_id, payload):
                            st.success(f"✅ 考核完成：{target_supplier} (总分 {avg_score:.1f})")
                            time.sleep(1)
                            st.rerun()

        with tab2:
            # 从独立的考核表拉取数据
            assess_records = connector.get_records(connector.assessment_table_id)
            if assess_records:
                df_assess = pd.DataFrame(assess_records)
                
                st.dataframe(
                    df_assess.drop(columns=["_record_id"], errors="ignore"),
                    use_container_width=True,
                    hide_index=True
                )
                
                with st.expander("🗑️ 删除考核记录"):
                    records_del = df_assess.to_dict('records')
                    sel_del = st.selectbox("选择记录删除", records_del, format_func=lambda x: f"{x.get('供应商')} - {x.get('录入时间')}")
                    if st.button("确认删除考核"):
                        if connector.delete_record(connector.assessment_table_id, sel_del["_record_id"]):
                            st.success("删除成功")
                            time.sleep(1)
                            st.rerun()
            else:
                st.info("考核表暂无数据，或字段未正确匹配。")
