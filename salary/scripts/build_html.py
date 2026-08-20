# -*- coding: utf-8 -*-
"""template.html にデータを埋め込んで、単一ファイルで完結する index.html を生成する。
生成物はネット接続不要・外部ファイル参照なしで動作する（Googleドライブ経由でiPhoneから開ける）。"""

import io
import json
import os
import shutil
import subprocess

import enrich

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(BASE, "scripts", "template.html")
OUT = os.path.join(BASE, "index.html")
DRIVE_DIR = r"G:\マイドライブ\プライベート\給与管理アプリ"
# iPhoneのChromeで開くWebアプリのURL（script.google.com/macros/s/{ID}/exec）を固定するため、
# 新規デプロイではなく既存デプロイメントIDを常に上書き更新する
APPSCRIPT_DIR = os.path.join(BASE, "appscript")
APPSCRIPT_DEPLOYMENT_ID = "AKfycbw4SX9Mj0vrqAODq-YMCTbStz1zqLkyak2EeaZ9gm5Z4RdC6mFGm7P8CYz2T0CDrOO1"

# dataviz スキルの検証済みパレット（light / dark 両モードで全チェック PASS）
EMP_META = {
    "saigai":   {"short": "災害医療センター",   "color": "#2a78d6", "dark": "#3987e5"},
    "hachioji": {"short": "八王子内科・消化器", "color": "#eb6834", "dark": "#d95926"},
    "terrace":  {"short": "立川クリニック",     "color": "#1baf7a", "dark": "#199e70"},
    "seikokai": {"short": "エヌ・エスクリニック", "color": "#eda100", "dark": "#c98500"},
}


def build_payload():
    d = enrich.build()
    if d["issues"]:
        raise SystemExit("データ不整合のため中止: %s" % d["issues"])

    t = d["totals"]
    gross = t["gross"]

    employers = []
    for e in d["employers"]:
        m = EMP_META[e["id"]]
        emp = d["by_emp"][e["id"]]
        # 所得税だけを抜き出す（乙欄源泉の可視化用）
        income_tax = emp["ded_items"].get("所得税", 0)
        employers.append({
            "id": e["id"],
            "name": e["name"],
            "short": m["short"],
            "role": e["role"],
            "color": m["color"],
            "dark": m["dark"],
            "gross": emp["gross"],
            "ded": emp["ded"],
            "net": emp["net"],
            "count": emp["count"],
            "incomeTax": income_tax,
            "incomeTaxRate": (income_tax / emp["gross"]) if emp["gross"] else 0,
            "netRate": (emp["net"] / emp["gross"]) if emp["gross"] else 0,
            "share": emp["gross"] / gross,
            "months": emp["months"],
            "earnItems": [{"name": k, "value": v} for k, v in emp["earn_items"].items()],
            "dedItems": [{"name": k, "value": v} for k, v in emp["ded_items"].items()],
            "hasSocialInsurance": any(
                enrich.classify_deduction(k) == "social" for k in emp["ded_items"]),
            "slips": [
                {
                    "month": s["month"],
                    "kind": s["kind"],
                    "gross": s["gross"],
                    "ded": s["ded_total"],
                    "net": s["net"],
                    "earnings": s["earnings"],
                    "deductions": s["deductions"],
                    "notes": s["notes"],
                    "file": s["source_file"],
                }
                for s in emp["slips"]
            ],
        })

    earn_cats = []
    for cid, meta in d["earning_categories"].items():
        v = d["earn_cat_totals"].get(cid, 0)
        if v:
            earn_cats.append({"id": cid, "label": meta["label"], "value": v, "pct": v / gross})

    ded_cats = []
    for cid, meta in d["deduction_categories"].items():
        v = d["ded_cat_totals"].get(cid, 0)
        if v:
            ded_cats.append({"id": cid, "label": meta["label"], "value": v, "pct": v / gross})

    ded_items = []
    cat_label = {k: v["label"] for k, v in d["deduction_categories"].items()}
    for name, v in sorted(d["item_totals"].items(), key=lambda kv: -kv[1]):
        ded_items.append({
            "name": name,
            "cat": enrich.classify_deduction(name),
            "catLabel": cat_label[enrich.classify_deduction(name)],
            "value": v,
            "pct": v / gross,
        })

    matrix = []
    for row in d["matrix"]:
        matrix.append({
            "month": row["month"],
            "gross": row["gross"],
            "ded": row["ded"],
            "net": row["net"],
            "byEmp": {k: v["gross"] for k, v in row["by_emp"].items()},
        })

    # 月次給与のみ（賞与を除く）の平均 → 年収ペースの推定に使う
    monthly_only = {}
    for s in d["slips"]:
        if s["kind"] == "monthly":
            monthly_only.setdefault(s["month"], 0)
            monthly_only[s["month"]] += s["gross"]
    bonus_total = sum(s["gross"] for s in d["slips"] if s["kind"] == "bonus")
    avg_monthly = sum(monthly_only.values()) / len(monthly_only) if monthly_only else 0

    ref = d["ref2025"]

    return {
        "meta": {
            "monthCount": t["months"],
            "slipCount": t["count"],
            "firstMonth": d["months"][0],
            "lastMonth": d["months"][-1],
            "year": d["months"][0][:4],
        },
        "totals": {
            "gross": gross,
            "ded": t["ded"],
            "net": t["net"],
            "netRate": t["net"] / gross,
            "dedRate": t["ded"] / gross,
            "avgMonthlyGross": avg_monthly,
            "bonusTotal": bonus_total,
            "projectedAnnual": avg_monthly * 12 + bonus_total,
            # 2026年の実績から算出した社会保険料の対総支給比（上限額シミュレーターの初期値に使う）
            "socialYtd": d["ded_cat_totals"].get("social", 0),
            "socialRatio": d["ded_cat_totals"].get("social", 0) / gross,
        },
        "employers": employers,
        "months": d["months"],
        "matrix": matrix,
        "earnCats": earn_cats,
        "dedCats": ded_cats,
        "dedItems": ded_items,
        "ref2025": {
            "salaryRevenue": ref["income"]["salary_revenue"],
            "employmentIncome": ref["income"]["employment_income"],
            "taxableIncome": ref["income"]["taxable_income"],
            "socialInsurance": ref["deductions"]["social_insurance"],
            "totalDeductions": ref["deductions"]["total_deductions"],
            "lifeInsurance": ref["deductions"]["life_insurance"],
            "earthquakeInsurance": ref["deductions"]["earthquake_insurance"],
            "smallBusiness": ref["deductions"]["small_business_mutual_aid"],
            "medicalDeduction": ref["deductions"]["medical_expense_deduction"],
            "basicDeduction": ref["deductions"]["basic_deduction"],
            "rtLifeInsurance": ref["resident_tax"]["life_insurance"],
            "rtEarthquakeInsurance": ref["resident_tax"]["earthquake_insurance"],
            "rtBasicDeduction": ref["resident_tax"]["basic_deduction"],
            "rtAdjustmentCredit": ref["resident_tax"]["adjustment_credit"],
            "rtIncomeLevy": ref["resident_tax"]["income_levy_before_credit"],
            "withholding": ref["tax"]["withholding_tax_total"],
            "refund": ref["tax"]["refund_amount"],
            "housingLoanCredit": ref["tax"]["housing_loan_credit"],
            "donation": ref["furusato_nozei_actual_2025"]["donation_total"],
            "donationIncomeTax": ref["furusato_nozei_actual_2025"]["income_tax_deduction_amount"],
            "donationResident": ref["furusato_nozei_actual_2025"]["resident_tax_deduction_total"],
            "actualLimit": ref["furusato_nozei_actual_2025"]["estimated_actual_limit"],
        },
    }


def main():
    payload = build_payload()
    with io.open(TEMPLATE, encoding="utf-8") as f:
        html = f.read()

    js = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if "/*__DATA__*/" not in html:
        raise SystemExit("template.html に /*__DATA__*/ プレースホルダがありません")
    html = html.replace("/*__DATA__*/", js)

    with io.open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print("generated:", OUT, "(%.1f KB)" % (os.path.getsize(OUT) / 1024.0))

    # Googleドライブの個人フォルダへ配布（iPhoneから開くため）
    if os.path.isdir(os.path.dirname(DRIVE_DIR)):
        if not os.path.isdir(DRIVE_DIR):
            os.makedirs(DRIVE_DIR)
        shutil.copy2(OUT, os.path.join(DRIVE_DIR, "index.html"))
        for name in ("payroll_2026.xlsx", "icon.svg", "manifest.json"):
            src = os.path.join(BASE, name)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(DRIVE_DIR, name))
        print("copied to:", DRIVE_DIR)
    else:
        print("Googleドライブが見つからないため配布はスキップしました")

    # iPhoneのChromeから開けるよう、Apps Script Webアプリにも反映する
    if os.path.isdir(APPSCRIPT_DIR):
        shutil.copy2(OUT, os.path.join(APPSCRIPT_DIR, "index.html"))
        try:
            subprocess.run(["clasp", "push", "--force"], cwd=APPSCRIPT_DIR, check=True, shell=True)
            subprocess.run(
                ["clasp", "deploy", "-i", APPSCRIPT_DEPLOYMENT_ID],
                cwd=APPSCRIPT_DIR, check=True, shell=True)
            print("Apps Script Webアプリを更新しました")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print("Apps Scriptへの反映に失敗しました（手動で `clasp push && clasp deploy` を実行してください）:", e)


if __name__ == "__main__":
    main()
