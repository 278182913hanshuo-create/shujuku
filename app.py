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
# 移除了所有对 Header、工具栏和装饰条的隐藏代码。
# 现在界面将恢复 Streamlit 的默认外观，确保侧边栏开关和功能菜单 100% 可用。
hide_streamlit_style = """
<style>
    /* 仅隐藏底部的 "Made with Streamlit" Footer */
    footer {
        visibility: hidden;
    }
    
    /* 仅隐藏右上角的 Deploy 按钮 (生产环境通常不需要用户看到此按钮) */
    .stDeployButton {
        display: none;
    }
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# --- 常量定义 ---
ASSESSMENT_TAG = "供应商考核"

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
                return []
        except Exception as e:
            return []

    def add_record(self, data_dict):
        """新增记录"""
        token = self.get_token()
        if not token: return False
        
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
        payload = {"fields": data_dict}
        
        try:
            response = requests.post(self.base_url, headers=headers, json=payload)
            res_json = response.json()
            
            if res_json.get("code") == 0:
                return True
            else:
                st.error(f"❌ 提交失败，飞书拒绝了请求。")
                return False
        except Exception:
            st.error("网络请求出错")
            return False

    def update_record(self, record_id, data_dict):
        """【新增】更新指定记录"""
        token = self.get_token()
        if not token: return False
        
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
        payload = {"fields": data_dict}
        url = f"{self.base_url}/{record_id}"
        
        try:
            response = requests.put(url, headers=headers, json=payload)
            res_json = response.json()
            
            if res_json.get("code") == 0:
                return True
            else:
                st.error(f"❌ 更新失败：{res_json.get('msg')}")
                return False
        except Exception:
            st.error("网络请求出错")
            return False

    def delete_record(self, record_id):
        """删除记录"""
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

    st.sidebar.title("北京富达采购数据库")
    
    if st.sidebar.button("🚪 退出登录"):
        st.session_state.authenticated = False
        st.rerun()
        
    menu = st.sidebar.radio("功能菜单", ["📊 数据查询", "➕ 录入报价", "📝 供应商考核"])

    # 获取现有数据
    existing_records = connector.get_records()
    df_columns = []
    if existing_records:
        df_columns = list(pd.DataFrame(existing_records).columns)
        if "_record_id" in df_columns: df_columns.remove("_record_id")

    # --- 功能 1: 数据查询 ---
    if menu == "📊 数据查询":
        st.title("📊 采购成本查询")
        
        if existing_records:
            df = pd.DataFrame(existing_records)
            
            if "单价" in df.columns and "询价单价" not in df.columns:
                df.rename(columns={"单价": "询价单价"}, inplace=True)

            if "设备类型" in df.columns:
                df = df[df["设备类型"] != ASSESSMENT_TAG]

            target_cols = ["供应商", "联系人", "设备类型", "询价单价", "录入时间", "备注"]
            display_cols = [c for c in target_cols if c in df.columns]
            
            final_df = df.copy()

            search_q = st.text_input("🔍 全局搜索", placeholder="输入关键字...")
            if search_q:
                mask = final_df.astype(str).apply(lambda x: x.str.contains(search_q, case=False)).any(axis=1)
                final_df = final_df[mask]

            # 重置索引，为了后续与 st.data_editor 返回的行号对齐
            final_df = final_df.reset_index(drop=True)

            st.write(f"共找到 **{len(final_df)}** 条记录。💡 **提示：直接双击下方表格的单元格即可修改内容，修改完成后请点击下方的“保存修改”按钮。**")
            
            # 【核心修改】将 st.dataframe 替换为 st.data_editor 以支持在线修改
            editor_data = final_df[display_cols] if display_cols else final_df
            
            st.data_editor(
                editor_data,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "询价单价": st.column_config.NumberColumn(format="¥ %.2f"),
                    "录入时间": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm", disabled=True), # 录入时间通常不允许被修改
                },
                key="db_editor"  # 设置 key 追踪修改状态
            )

            # --- 保存修改按钮 ---
            if st.button("💾 保存表格修改", type="primary"):
                # 获取被修改的数据
                edits = st.session_state.get("db_editor", {}).get("edited_rows", {})
                
                if not edits:
                    st.warning("您还没有修改任何单元格。请双击表格编辑后再点击保存。")
                else:
                    success_count = 0
                    with st.spinner("正在将修改同步至飞书数据库..."):
                        for idx_str, changes in edits.items():
                            idx = int(idx_str)
                            real_record_id = final_df.iloc[idx]["_record_id"]
                            
                            payload = {}
                            for col, val in changes.items():
                                # 将 UI 显示的“询价单价”映射回飞书真实的“单价”字段
                                if col == "询价单价" and "单价" in df_columns and "询价单价" not in df_columns:
                                    payload["单价"] = val
                                else:
                                    payload[col] = val
                            
                            if payload:
                                if connector.update_record(real_record_id, payload):
                                    success_count += 1
                                    
                    if success_count > 0:
                        st.success(f"✅ 成功更新了 {success_count} 条记录！")
                        time.sleep(1)
                        st.rerun()

            # --- 删除功能 ---
            with st.expander("🗑️ 删除记录"):
                if not final_df.empty:
                    records_to_delete = final_df.to_dict('records')
                    def fmt_func(row):
                        sup = row.get("供应商", "未知")
                        dev = row.get("设备类型", "未知")
                        return f"{sup} - {dev}"

                    selected_row = st.selectbox("选择要删除的行", records_to_delete, format_func=fmt_func)
                    if st.button("确认删除"):
                        if connector.delete_record(selected_row["_record_id"]):
                            st.success("删除成功！")
                            time.sleep(1)
                            st.rerun()
        else:
            st.info("表格为空或连接失败。")

    # --- 功能 2: 录入报价 ---
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
            
            submitted = st.form_submit_button("🚀 提交")

            if submitted:
                if not supplier:
                    st.warning("请填写供应商名称")
                else:
                    price_key = "询价单价"
                    if "询价单价" not in df_columns and "单价" in df_columns:
                        price_key = "单价"

                    payload = {
                        "供应商": supplier,
                        "联系人": contact,
                        "设备类型": device,
                        price_key: price,
                        "备注": note,
                        "录入时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    
                    clean_payload = {k: v for k, v in payload.items() if v}
                    
                    if connector.add_record(clean_payload):
                        st.success(f"✅ 已录入：{supplier} - {device}")
                        time.sleep(1)
                        st.rerun()

    # --- 功能 3: 供应商考核 ---
    elif menu == "📝 供应商考核":
        st.title("📝 供应商绩效考核")
        
        tab1, tab2 = st.tabs(["➕ 新建考核", "📜 历史考核记录"])
        
        with tab1:
            st.info("考核结果将自动保存至数据库，请客观评分。")
            
            supplier_list = []
            if existing_records:
                df_temp = pd.DataFrame(existing_records)
                if "供应商" in df_temp.columns:
                    supplier_list = df_temp["供应商"].dropna().unique().tolist()

            with st.form("assessment_form"):
                if supplier_list:
                    target_supplier = st.selectbox("选择被考核供应商", supplier_list)
                else:
                    target_supplier = st.text_input("被考核供应商名称")
                
                st.divider()
                col1, col2 = st.columns(2)
                
                with col1:
                    score_quality = st.slider("产品质量评分 (40%)", 0, 100, 80)
                    score_delivery = st.slider("交付及时性评分 (30%)", 0, 100, 80)
                
                with col2:
                    score_price = st.slider("价格竞争力评分 (20%)", 0, 100, 80)
                    score_service = st.slider("售后服务评分 (10%)", 0, 100, 80)
                
                comments = st.text_area("考核评语/改进建议")
                
                submitted = st.form_submit_button("📤 提交考核结果")
                
                if submitted:
                    if not target_supplier:
                        st.warning("请选择或填写供应商名称")
                    else:
                        avg_score = (score_quality + score_delivery + score_price + score_service) / 4
                        
                        detail_note = (
                            f"【年度考核】总分: {avg_score:.1f}\n"
                            f"质量: {score_quality} | 交付: {score_delivery} | 价格: {score_price} | 服务: {score_service}\n"
                            f"评语: {comments}"
                        )

                        price_key = "询价单价"
                        if "询价单价" not in df_columns and "单价" in df_columns:
                            price_key = "单价"
                        
                        payload = {
                            "供应商": target_supplier,
                            "设备类型": ASSESSMENT_TAG, 
                            "联系人": "考核系统",
                            price_key: 0,
                            "备注": detail_note,
                            "录入时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        
                        if connector.add_record(payload):
                            st.success(f"✅ 考核完成：{target_supplier} (总分 {avg_score:.1f})")
                            time.sleep(1)
                            st.rerun()

        with tab2:
            if existing_records:
                df_assess = pd.DataFrame(existing_records)
                
                if "设备类型" in df_assess.columns:
                    df_assess = df_assess[df_assess["设备类型"] == ASSESSMENT_TAG]
                
                if df_assess.empty:
                    st.info("暂无历史考核记录")
                else:
                    assess_cols = ["供应商", "录入时间", "备注"]
                    final_assess = df_assess[assess_cols].copy() if set(assess_cols).issubset(df_assess.columns) else df_assess
                    
                    st.dataframe(
                        final_assess,
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "录入时间": st.column_config.DatetimeColumn(format="YYYY-MM-DD"),
                            "备注": st.column_config.TextColumn("考核详情", width="large")
                        }
                    )
                    
                    with st.expander("🗑️ 删除考核记录"):
                        records_del = df_assess.to_dict('records')
                        def assess_fmt(row):
                            return f"{row.get('供应商')} - {row.get('录入时间')} "
                        
                        sel_del = st.selectbox("选择记录删除", records_del, format_func=assess_fmt)
                        if st.button("确认删除考核"):
                            if connector.delete_record(sel_del["_record_id"]):
                                st.success("删除成功")
                                time.sleep(1)
                                st.rerun()
            else:
                st.info("暂无数据")
