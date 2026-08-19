from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def public_home() -> HTMLResponse:
    return HTMLResponse(
        """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
  <title>PODX AI CONNECT</title>
  <meta name=\"description\" content=\"PODX AI CONNECT helps people find and connect with relevant products, services, jobs, businesses and local opportunities.\">
  <style>
    body{font-family:Arial,sans-serif;margin:0;background:#f7f8fb;color:#16181d}
    main{max-width:900px;margin:0 auto;padding:64px 24px}
    .card{background:#fff;border:1px solid #e7e9ee;border-radius:20px;padding:36px;box-shadow:0 10px 30px rgba(0,0,0,.05)}
    h1{font-size:42px;margin:0 0 12px} h2{margin-top:34px}
    p{font-size:18px;line-height:1.6;color:#454b57}
    .pill{display:inline-block;padding:8px 12px;border-radius:999px;background:#eef3ff;margin:5px 5px 0 0}
    footer{margin-top:30px;color:#697180;font-size:14px}
  </style>
</head>
<body>
<main>
  <section class=\"card\">
    <h1>PODX AI CONNECT</h1>
    <p>AI-powered requirement and connection platform helping users discover suitable local and online options without forcing a purchase.</p>
    <div>
      <span class=\"pill\">Products</span><span class=\"pill\">Services</span><span class=\"pill\">Jobs</span><span class=\"pill\">Local Commerce</span><span class=\"pill\">Business Leads</span>
    </div>
    <h2>How PODX works</h2>
    <p>Users tell PODX what they need. PODX helps understand the requirement, compare relevant options and connect the user to the appropriate seller, service provider, merchant or authorised partner. Final choice always remains with the user.</p>
    <h2>Trust-first recommendations</h2>
    <p>PODX is designed to prioritise relevance, suitability and user outcome. Affiliate or referral relationships do not decide which option is recommended.</p>
    <footer>Official public page for PODX AI CONNECT.</footer>
  </section>
</main>
</body>
</html>"""
    )
