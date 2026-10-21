"""Embed the city data and the current integrated plan into mashup_page.html -> street_mashup.html.
Usage: python3 -I build_page.py [plan.json]   (default: ../../Saved/Mashup/plan_v2.json)"""
import json, pathlib, sys
here = pathlib.Path(__file__).resolve().parent
plan_path = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else here.parents[1] / "Saved" / "Mashup" / "plan_v2.json"
data = (here / "mashup_data.json").read_text().replace("</", "<\\/")
plan = json.load(open(plan_path))
plan.pop("layout", None); plan.pop("stats", None)
plan_txt = json.dumps(plan, separators=(",", ":")).replace("</", "<\\/")
page = (here / "mashup_page.html").read_text().replace("__CITY_DATA__", data).replace("__PLAN_DATA__", plan_txt)
(here / "street_mashup.html").write_text(page)
print("street_mashup.html", round(len(page) / 1e6, 2), "MB")
