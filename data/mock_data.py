"""
Mock data generator for the anti-abuse ATO system.

Generates:
  - 100,000 users with realistic distributions.
  - UserProfiles with Zipf-distributed connection counts.
  - Up to 2 months of interactions with varied frequency per user.

Design notes on realism:
  - ~10% of users use hosting IPs (potential bot/VPN).
  - ~5% of users are inactive (closed accounts).
  - Interaction frequency follows a power-law distribution:
    most users have few interactions, some are very active.
  - Connections follow a Zipf distribution (many low, few high).
  - Account creation is the first event in every user's history.
  - No interactions occur after a CLOSE_ACCOUNT event.
  - Some users switch IPs between interactions (VPN/proxy).
  - User agents vary: ~12% of users use non-browser UAs
    (API clients, bots, mobile apps, scripts).
  - Not all users have 2 full months of interactions — users
    who joined recently have proportionally shorter histories.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone

from core.constants import (
    GENERATION_PATTERN_CLEAN,
    INTERACTION_WINDOW_DAYS,
    NUM_ACCOUNT_FARMING_ACCOUNTS,
    NUM_COVERT_PORN_ACCOUNTS,
    NUM_FAKE_ACCOUNTS,
    NUM_HARASSMENT_ACCOUNTS,
    NUM_LIKE_INFLATION_ACCOUNTS,
    NUM_PHARMACY_ACCOUNTS,
    NUM_USERS,
)
from core.enums import InteractionType, IPType
from core.models import User, UserInteraction, UserProfile
from data.config_utils import get_cfg
from data.non_fraud import generate_legitimate_events

# ---------------------------------------------------------------------------
# Mock-data-specific constants (not in core.constants)
# ---------------------------------------------------------------------------
# IPs used by fake account creation rings (same country, shared across accounts)
_FAKE_ACCOUNT_IP_POOL_RU = [
    "91.185.32.12", "91.185.32.45", "91.185.32.78", "91.185.33.10", "91.185.33.55",
    "91.185.34.22", "91.185.35.67", "91.186.12.88", "91.186.13.101", "91.186.14.203",
    "95.165.28.45", "95.165.29.112", "95.165.30.78", "185.71.45.33", "185.71.46.90",
    "188.170.22.156", "188.170.23.77", "193.104.88.12", "194.58.12.34", "195.24.156.89",
]

# Country weights (rough population / internet-user distribution)
_COUNTRY_WEIGHTS = {
    "US": 20, "IN": 15, "BR": 8, "GB": 7, "DE": 6, "FR": 5, "JP": 5,
    "CA": 4, "AU": 3, "KR": 3, "MX": 3, "ID": 3, "PH": 3, "TR": 2,
    "RU": 2, "NG": 2, "PL": 2, "NL": 2, "SE": 1, "IT": 2,
    "ES": 2, "ZA": 1, "EG": 1, "CN": 3, "VN": 2, "PK": 2,
    "UA": 1, "RO": 1, "BD": 1, "TH": 1,
}
_COUNTRIES = list(_COUNTRY_WEIGHTS.keys())
_COUNTRY_W = list(_COUNTRY_WEIGHTS.values())

# Languages per country (tuples for multi-language countries)
_COUNTRY_LANG: dict[str, tuple[str, ...]] = {
    "US": ("en", "es"),
    "GB": ("en",),
    "CA": ("en", "fr"),
    "AU": ("en",),
    "IN": ("hi", "en"),
    "BR": ("pt",),
    "DE": ("de",),
    "FR": ("fr",),
    "JP": ("ja",),
    "KR": ("ko",),
    "MX": ("es",),
    "NG": ("en",),
    "RU": ("ru",),
    "CN": ("zh",),
    "ID": ("id",),
    "PH": ("tl", "en"),
    "TR": ("tr",),
    "EG": ("ar",),
    "PK": ("hi", "en"),
    "BD": ("bn",),
    "VN": ("vi",),
    "IT": ("it",),
    "ES": ("es", "ca"),
    "NL": ("nl",),
    "SE": ("sv",),
    "PL": ("pl",),
    "UA": ("uk",),
    "RO": ("ro",),
    "ZA": ("en", "af"),
    "TH": ("th",),
}

# First-name pools (simplified)
_FIRST_NAMES = [
    "James", "Mary", "Amit", "Priya", "Carlos", "Maria", "Hans", "Sophie",
    "Yuki", "Hana", "Wei", "Lin", "Ahmed", "Fatima", "Olga", "Ivan",
    "Kofi", "Ama", "Luis", "Ana", "Kim", "Ji-yeon", "Thiago", "Fernanda",
    "Raj", "Sita", "Mohammed", "Aisha", "Pierre", "Claire", "Luca", "Giulia",
    "Sven", "Ingrid", "Jan", "Eva", "Oleg", "Natasha", "Chen", "Mei",
    "Kenji", "Sakura", "David", "Sarah", "Michael", "Emma", "Daniel", "Laura",
    "Robert", "Jennifer", "Christopher", "Lisa", "Matthew", "Amanda", "Anthony", "Melissa",
    "Mark", "Stephanie", "Donald", "Rebecca", "Steven", "Laura", "Paul", "Nicole",
    "Andrew", "Elizabeth", "Joshua", "Megan", "Kenneth", "Heather", "Kevin", "Rachel",
    "Brian", "Samantha", "George", "Christina", "Timothy", "Amy", "Ronald", "Michelle",
    "Edward", "Angela", "Jason", "Tiffany", "Jeffrey", "Kelly", "Ryan", "Diana",
    "Jacob", "Ashley", "Gary", "Kimberly", "Nicholas", "Emily", "Eric", "Donna",
    "Jonathan", "Carol", "Stephen", "Michelle", "Larry", "Patricia", "Justin", "Deborah",
    "Scott", "Dorothy", "Brandon", "Karen", "Benjamin", "Betty", "Samuel", "Helen",
    "Raymond", "Sandra", "Gregory", "Ashley", "Frank", "Katherine", "Alexander", "Margaret",
]

_LAST_NAMES = [
    "Smith", "Kumar", "Silva", "Müller", "Tanaka", "Wang", "Ali", "Kim",
    "Garcia", "Johansson", "Nowak", "Petrov", "Brown", "Johnson", "Williams",
    "Okafor", "Santos", "Nguyen", "Lee", "Chen", "Andersen", "Dubois",
    "Rossi", "Fernandez", "Martinez", "Lopez", "Gonzalez", "Wilson", "Taylor",
    "Anderson", "Thomas", "Jackson", "White", "Harris", "Martin", "Thompson",
    "Moore", "Robinson", "Clark", "Lewis", "Rodriguez", "Walker", "Hall",
    "Young", "Allen", "King", "Wright", "Scott", "Green", "Baker",
    "Adams", "Nelson", "Hill", "Campbell", "Mitchell", "Roberts", "Carter",
    "Phillips", "Evans", "Turner", "Torres", "Parker", "Collins", "Edwards",
    "Stewart", "Flores", "Morris", "Murphy", "Rivera", "Cook", "Rogers",
    "Morgan", "Peterson", "Cooper", "Reed", "Bailey", "Bell", "Gomez",
    "Kelly", "Howard", "Ward", "Cox", "Diaz", "Richardson", "Wood", "Watson",
    "Brooks", "Bennett", "Gray", "James", "Reyes", "Cruz", "Hughes", "Price",
    "Myers", "Long", "Foster", "Sanders", "Ross", "Morales", "Powell", "Sullivan",
]

# Spanish first/last names, headlines, summaries
_FIRST_NAMES_ES = [
    "Carlos", "María", "José", "Ana", "Antonio", "Francisco", "Miguel", "Carmen",
    "David", "Laura", "Pablo", "Elena", "Javier", "Sara", "Daniel", "Isabel",
    "Alejandro", "Lucía", "Manuel", "Paula", "Raúl", "Sofía", "Pedro", "Claudia",
]
_LAST_NAMES_ES = [
    "García", "Rodríguez", "Martínez", "López", "González", "Fernández", "Pérez", "Sánchez",
    "Ramírez", "Torres", "Flores", "Rivera", "Gómez", "Díaz", "Reyes", "Morales",
    "Hernández", "Jiménez", "Ruiz", "Ortiz", "Moreno", "Álvarez", "Romero", "Castillo",
]
_HEADLINES_ES = [
    "Ingeniero de Software", "Director de Producto", "Científico de Datos",
    "Director de Marketing", "Diseñador UX", "Ejecutivo de Ventas",
    "Desarrollador Full Stack", "Analista de Negocios", "Gerente de RRHH",
    "Ingeniero DevOps", "CEO y Fundador", "Consultor",
    "Estudiante", "Escritor Freelance", "Diseñador Gráfico",
    "Ingeniero Aeroespacial", "Piloto comercial", "Arquitecto de Software",
]
_SUMMARIES_ES = [
    "Apasionado por crear grandes productos.",
    "Profesional con más de 10 años de experiencia.",
    "Buscando nuevas oportunidades y conexiones.",
    "Me encanta colaborar en equipo para resolver problemas difíciles.",
    "Enfocado en impulsar el crecimiento y la innovación.",
    "Comprometido con el aprendizaje continuo.",
    "Entusiasta de la tecnología y su impacto en la sociedad.",
    "Ayudando a equipos a ser más rápidos y eficientes.",
    "Siempre curioso. Siempre aprendiendo.",
    "Conectando personas e ideas.",
    "Construyendo el futuro, un commit a la vez.",
    "Experto en sistemas distribuidos y escalabilidad.",
    "Apasionado por la experiencia de usuario.",
    "Ex fundador de startups. Ahora asesorando e invirtiendo.",
    "",  # Algunos usuarios dejan el resumen vacío
]

# German first/last names, headlines, summaries
_FIRST_NAMES_DE = [
    "Hans", "Anna", "Peter", "Maria", "Michael", "Lisa", "Thomas", "Julia",
    "Andreas", "Sarah", "Stefan", "Laura", "Christian", "Jennifer", "Markus", "Jessica",
    "Florian", "Katharina", "Alexander", "Christina", "Martin", "Sabine", "Daniel", "Nina",
]
_LAST_NAMES_DE = [
    "Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner", "Becker",
    "Schulz", "Hoffmann", "Koch", "Richter", "Klein", "Wolf", "Schröder", "Neumann",
    "Schwarz", "Zimmermann", "Braun", "Krüger", "Hartmann", "Lange", "Schmitt", "Werner",
]
_HEADLINES_DE = [
    "Software-Ingenieur", "Produktmanager", "Data Scientist",
    "Marketing-Direktor", "UX-Designer", "Vertriebsleiter",
    "Full-Stack-Entwickler", "Business Analyst", "Personalmanager",
    "DevOps-Ingenieur", "CEO & Gründer", "Berater",
    "Student", "Freier Schriftsteller", "Grafikdesigner",
    "Luftfahrtingenieur", "Linienpilot", "Software-Architekt",
]
_SUMMARIES_DE = [
    "Leidenschaftlich daran, großartige Produkte zu entwickeln.",
    "Erfahrener Profi mit über 10 Jahren Branchenerfahrung.",
    "Suche nach neuen Möglichkeiten und Kontakten.",
    "Arbeite gerne im Team an schwierigen Problemen.",
    "Fokus auf Wachstum und Innovation.",
    "Engagiert für kontinuierliches Lernen.",
    "Begeistert von Technologie und ihrer Wirkung.",
    "Helfe Teams, schneller und smarter zu arbeiten.",
    "Immer neugierig. Immer am Lernen.",
    "Verbinde Menschen und Ideen.",
    "Baue die Zukunft, ein Commit nach dem anderen.",
    "Experte für verteilte Systeme und Skalierung.",
    "Leidenschaft für Nutzererlebnis und Barrierefreiheit.",
    "Ehemaliger Startup-Gründer. Jetzt Beratung und Investition.",
    "",  # Manche Nutzer lassen die Zusammenfassung leer
]

# Japanese first/last names (kanji), headlines, summaries
_FIRST_NAMES_JA = [
    "浩", "由紀", "武", "桜", "健二", "花", "悠人", "愛子",
    "陽翔", "芽", "颯太", "凛", "海斗", "美羽", "陸", "空",
    "大輝", "陽葵", "蓮", "結衣", "翔太", "真奈", "隼人", "明里",
]
_LAST_NAMES_JA = [
    "田中", "鈴木", "高橋", "渡辺", "山本", "山田", "佐藤", "斎藤",
    "小林", "加藤", "吉田", "山口", "松本", "井上", "木村", "林",
    "清水", "森", "阿部", "池田", "橋本", "山下", "石川", "中島",
]
_HEADLINES_JA = [
    "ソフトウェアエンジニア", "プロダクトマネージャー", "データサイエンティスト",
    "マーケティングディレクター", "UXデザイナー", "営業担当",
    "フルスタック開発者", "ビジネスアナリスト", "人事マネージャー",
    "DevOpsエンジニア", "CEO・創業者", "コンサルタント",
    "学生", "フリーランスライター", "グラフィックデザイナー",
    "航空宇宙エンジニア", "パイロット", "ソフトウェアアーキテクト",
]
_SUMMARIES_JA = [
    "素晴らしいプロダクトを作ることに情熱を注いでいます。",
    "10年以上の経験を持つプロフェッショナルです。",
    "新しい機会とつながりを探しています。",
    "チームで難しい問題を解決するのが好きです。",
    "成長とイノベーションに注力しています。",
    "継続的な学習と改善に取り組んでいます。",
    "技術と社会への影響に熱心です。",
    "チームの効率化をお手伝いします。",
    "常に好奇心を持ち、学び続けています。",
    "人とアイデアをつなぎます。",
    "一つのコミットから未来を築いています。",
    "分散システムとスケーラビリティの専門家です。",
    "ユーザー体験とアクセシビリティに情熱を注いでいます。",
    "元スタートアップ創業者。今はアドバイザーと投資家。",
    "",  # 要約を空欄にするユーザーもいます
]

# Language -> (first_names, last_names, headlines, summaries) for genuine users
_LANG_CONTENT: dict[str, tuple[list[str], list[str], list[str], list[str]]] = {
    "es": (_FIRST_NAMES_ES, _LAST_NAMES_ES, _HEADLINES_ES, _SUMMARIES_ES),
    "de": (_FIRST_NAMES_DE, _LAST_NAMES_DE, _HEADLINES_DE, _SUMMARIES_DE),
    "ja": (_FIRST_NAMES_JA, _LAST_NAMES_JA, _HEADLINES_JA, _SUMMARIES_JA),
}


def _get_content_for_lang(lang: str) -> tuple[list[str], list[str], list[str], list[str]]:
    """Return (first_names, last_names, headlines, summaries) for the given language."""
    if lang in _LANG_CONTENT:
        return _LANG_CONTENT[lang]
    return (_FIRST_NAMES, _LAST_NAMES, _HEADLINES, _SUMMARIES)


# Email domains (weights approximate real-world distribution)
_EMAIL_DOMAINS = [
    "gmail.com", "outlook.com", "yahoo.com", "hotmail.com", "icloud.com",
    "protonmail.com", "mail.com", "aol.com", "zoho.com", "yandex.com",
    "gmx.com", "live.com", "msn.com", "qq.com", "163.com", "btinternet.com",
]
_EMAIL_DOMAIN_WEIGHTS = [25, 15, 12, 8, 6, 4, 3, 3, 2, 2, 2, 2, 1, 2, 1, 3]

_HEADLINES = [
    "Software Engineer", "Product Manager", "Data Scientist",
    "Marketing Director", "UX Designer", "Sales Executive",
    "Full Stack Developer", "Business Analyst", "HR Manager",
    "DevOps Engineer", "CEO & Founder", "Consultant",
    "Student", "Freelance Writer", "Graphic Designer",
    "Research Scientist", "Account Manager", "Operations Lead",
    "Cloud Architect", "Machine Learning Engineer",
    "Senior Developer", "Technical Lead", "Scrum Master",
    "Project Manager", "Finance Analyst", "Legal Counsel",
    "Teacher", "Nurse", "Architect", "Designer",
    "Entrepreneur", "Investor", "Recruiter", "Copywriter",
    "Data Analyst", "Frontend Developer", "Backend Engineer",
    "Security Engineer", "QA Engineer", "Support Specialist",
    "Solutions Architect", "Growth Hacker", "Content Strategist",
    "Customer Success Manager", "Supply Chain Manager", "Brand Manager",
    "Engineering Manager", "VP of Product", "Chief of Staff",
    "Compliance Officer", "Risk Analyst", "Treasury Analyst",
    "Business Development Lead", "Partnership Manager", "Channel Sales",
    "Infrastructure Engineer", "Site Reliability Engineer", "Platform Engineer",
    "Mobile Developer", "iOS Developer", "Android Developer",
    "Blockchain Developer", "Game Developer", "Embedded Engineer",
    "Technical Writer", "Documentation Specialist", "Community Manager",
    "Social Media Manager", "Digital Marketing Lead", "SEO Specialist",
    "Event Coordinator", "Office Manager", "Executive Assistant",
    "Physician", "Software Architect", "Principal Engineer",
    "Director of Engineering", "CTO", "COO",
    "Sales Director", "Regional Manager", "Territory Representative",
    "Logistics Coordinator", "Manufacturing Lead", "Quality Assurance",
    "Auditor", "Tax Consultant", "Insurance Advisor",
    "Real Estate Agent", "Urban Planner", "Civil Engineer",
    "Mechanical Engineer", "Electrical Engineer", "Chemical Engineer",
    "Biologist", "Pharmacist", "Veterinarian",
    "Chef", "Photographer", "Videographer",
    "Musician", "Artist", "Interior Designer",
    "Public Relations Manager", "Journalist", "Editor",
    "Aerospace Engineer", "Aircraft Design Engineer", "Flight Test Engineer",
    "Avionics Engineer", "Propulsion Engineer", "Aerodynamics Specialist",
    "Commercial Pilot", "Flight Instructor", "Airline Captain",
    "Aerospace Systems Analyst", "Aircraft Maintenance Engineer", "Flight Operations Manager",
    "Spacecraft Engineer", "Satellite Systems Engineer", "Mission Control Specialist",
]

_SUMMARIES = [
    "Passionate about building great products.",
    "Experienced professional with 10+ years in the industry.",
    "Looking for new opportunities and connections.",
    "Love collaborating across teams to solve hard problems.",
    "Focused on driving growth and innovation.",
    "Dedicated to continuous learning and improvement.",
    "Enthusiastic about technology and its impact on society.",
    "Previously at FAANG. Now building something new.",
    "Helping teams ship faster and smarter.",
    "Always curious. Always learning.",
    "Connecting people and ideas.",
    "Building the future, one commit at a time.",
    "Expert in distributed systems and scaling.",
    "Passionate about user experience and accessibility.",
    "Former startup founder. Now advising and investing.",
    "Love mentoring and growing technical teams.",
    "Open source contributor. Python and Go enthusiast.",
    "15 years in fintech. Now exploring AI/ML.",
    "Making complex things simple.",
    "Believe in work-life balance and sustainable pace.",
    "Driving digital transformation across organizations.",
    "Specializing in high-performance systems and scale.",
    "Customer-obsessed. Data-driven. Results-focused.",
    "Building products that matter.",
    "Ex-consultant. Now scaling startups.",
    "Passionate about clean code and great design.",
    "Connecting technology with business outcomes.",
    "Bringing ideas to life through code.",
    "Advocate for inclusive design and accessibility.",
    "Helping companies navigate cloud and infrastructure.",
    "Experienced in B2B SaaS and enterprise sales.",
    "Building and scaling high-performing teams.",
    "Focused on product-market fit and growth.",
    "Strategic thinker with execution bias.",
    "Bringing operational excellence to startups.",
    "Cross-functional leader. Problem solver.",
    "Expert in agile and lean methodologies.",
    "Turning data into actionable insights.",
    "Committed to sustainable business practices.",
    "Networker. Connector. Relationship builder.",
    "Former journalist. Now in tech.",
    "Dual background in engineering and business.",
    "Helping founders tell their story.",
    "Building communities and brand loyalty.",
    "Specializing in go-to-market strategy.",
    "Love the intersection of design and engineering.",
    "Bridge between technical and non-technical teams.",
    "Optimizing processes and removing friction.",
    "Creating memorable user experiences.",
    "Making healthcare more accessible through technology.",
    "Passionate about education and learning platforms.",
    "Building tools for creators and makers.",
    "Exploring the future of work.",
    "Committed to ethical AI and responsible tech.",
    "Aerospace engineer specializing in structural design and fatigue analysis.",
    "Pilot. Aviation enthusiast. Safety-first mindset.",
    "15 years in aircraft maintenance and certification.",
    "Building the future of flight. Previously at major OEMs.",
    "Passionate about sustainable aviation and hybrid propulsion.",
    "Flight test engineer. Turning specs into validated aircraft.",
    "Avionics and flight control systems. Love complex systems.",
    "From military aviation to commercial. Still flying.",
    "Spacecraft systems engineer. Mission-critical experience.",
    "Aerodynamics and CFD. Making things fly efficiently.",
    "Airline operations and fleet management experience.",
    "Bringing aerospace rigor to new ventures.",
    "",  # Some users leave summary empty
]

# Fishy pharmacy profiles: fronts for foreign "pharmacies" using covert drug names
_PHARMACY_HEADLINES = [
    "International Pharmacy Consultant", "Healthcare Advisor", "Medication Specialist",
    "Global Wellness Supplier", "Pharmacy Liaison", "Health Products Distributor",
    "Online Pharmacy Representative", "European Pharmacies Partner",
    "Alternative Medicine Provider", "Prescription Services Coordinator",
]
_PHARMACY_WEBSITES = [
    "https://meds-express.in", "https://pharma24.mx", "https://rx-shop.co.in",
    "https://meds-express-turkey.com", "https://pharma365.ru",
    "https://cheap-rx-thailand.net", "https://generic-pharma.pk",
    "https://meds-express-ph.com", "https://rx-vietnam.com",
    "https://pharma-express.co.uk", "https://canada-rx.net",
]
_PHARMACY_SUMMARIES = [
    "Discrete worldwide shipping. Quality products. Visit our site for skittles, beans, and candy. No prescription needed.",
    "Trusted source for molly, E, and rolls. Fast delivery from multiple locations. Contact us.",
    "Premium oxy, blues, percs. Best prices. Visit {url} for catalog.",
    "We carry green, bud, herb. Wholesale and retail. Orders at {url}",
    "Reliable delivery of boy, H, dope. Discreet packaging. {url}",
    "Snow, white, powder available. Multiple international locations. {url}",
    "Bars, xans, xannies in stock. EU and Asia shipping. Visit {url}",
    "Addy, speed, uppers. Fast delivery. {url}",
    "Downers, zans, tranqs. Quality guaranteed. Visit {url} for menu.",
]

# Fishy covert porn profiles: fronts using euphemistic adult content
_PORN_HEADLINES = [
    "Adult Content Creator", "Entertainment Industry Pro", "Premium Content Producer",
    "Independent Creator", "Digital Media Artist", "Exclusive Content Provider",
    "Lifestyle Content Creator", "Cam Model Representative", "Fan Club Manager",
    "Adult Entertainment Liaison",
]
_PORN_WEBSITES = [
    "https://premium-content.co", "https://exclusive-fans.net", "https://adult-cam.live",
    "https://private-shows.eu", "https://fan-club-xxx.ru", "https://adult-dating.in",
    "https://premium-pics.co.uk", "https://private-vids.com", "https://exclusive-only.net",
    "https://adult-entertainment.mx",
]
_PORN_SUMMARIES = [
    "Exclusive content. Premium pics and vids. DM for link. Visit {url}",
    "Private shows available. 18+ only. Discreet. {url}",
    "Fan club with exclusive content. Multiple platforms. Link in bio: {url}",
    "Adult entertainment. Cam sessions. Worldwide. {url}",
    "Premium adult content. No limits. {url}",
    "Exclusive uncensored content. {url}",
    "Private adult content creator. DM for menu. {url}",
    "18+ premium entertainment. Various formats. {url}",
]

# Bogus profiles filled by account-farming buyers
_FARMING_HEADLINES = [
    "Freelancer", "Looking for opportunities", "Open to work",
    "Entrepreneur", "Consultant", "Independent",
]
_FARMING_SUMMARIES = [
    "Just getting started. Open to new connections.",
    "Building my network. Connect with me!",
    "Here to learn and grow. Let's connect.",
]

_LOCATIONS = [
    "San Francisco, CA", "New York, NY", "London, UK", "Berlin, Germany",
    "Tokyo, Japan", "Mumbai, India", "São Paulo, Brazil", "Sydney, Australia",
    "Toronto, Canada", "Seoul, South Korea", "Paris, France", "Amsterdam, Netherlands",
    "Stockholm, Sweden", "Warsaw, Poland", "Mexico City, Mexico",
    "Lagos, Nigeria", "Moscow, Russia", "Shanghai, China", "Ho Chi Minh City, Vietnam",
    "Manila, Philippines", "Istanbul, Turkey", "Cairo, Egypt", "Karachi, Pakistan",
    "Dhaka, Bangladesh", "Bangkok, Thailand", "Rome, Italy", "Madrid, Spain",
    "Cape Town, South Africa", "Kyiv, Ukraine", "Bucharest, Romania",
    "Seattle, WA", "Chicago, IL", "Austin, TX", "Boston, MA", "Denver, CO",
    "Vancouver, BC", "Melbourne, Australia", "Singapore", "Hong Kong",
    "Dublin, Ireland", "Zurich, Switzerland", "Barcelona, Spain",
    "Los Angeles, CA", "Houston, TX", "Phoenix, AZ", "Philadelphia, PA", "San Antonio, TX",
    "San Diego, CA", "Dallas, TX", "San Jose, CA", "Indianapolis, IN", "Jacksonville, FL",
    "Columbus, OH", "Charlotte, NC", "Milwaukee, WI", "Baltimore, MD", "Portland, OR",
    "Atlanta, GA", "Miami, FL", "Minneapolis, MN", "Detroit, MI", "Las Vegas, NV",
    "Munich, Germany", "Hamburg, Germany", "Cologne, Germany", "Frankfurt, Germany",
    "Lyon, France", "Marseille, France", "Toulouse, France", "Bordeaux, France",
    "Milan, Italy", "Naples, Italy", "Turin, Italy", "Florence, Italy",
    "Oslo, Norway", "Copenhagen, Denmark", "Helsinki, Finland", "Reykjavik, Iceland",
    "Prague, Czech Republic", "Vienna, Austria", "Budapest, Hungary", "Lisbon, Portugal",
    "Athens, Greece", "Belgrade, Serbia", "Sofia, Bulgaria", "Zagreb, Croatia",
    "Buenos Aires, Argentina", "Lima, Peru", "Bogotá, Colombia", "Santiago, Chile",
    "Medellín, Colombia", "Quito, Ecuador", "Montevideo, Uruguay", "Caracas, Venezuela",
    "Johannesburg, South Africa", "Nairobi, Kenya", "Accra, Ghana", "Addis Ababa, Ethiopia",
    "Casablanca, Morocco", "Algiers, Algeria", "Tunis, Tunisia",
    "Jakarta, Indonesia", "Kuala Lumpur, Malaysia", "Taipei, Taiwan", "Hanoi, Vietnam",
    "Beijing, China", "Shenzhen, China", "Guangzhou, China", "Chengdu, China",
    "Delhi, India", "Bangalore, India", "Chennai, India", "Hyderabad, India",
    "Kolkata, India", "Ahmedabad, India", "Pune, India",
    "Auckland, New Zealand", "Wellington, New Zealand", "Christchurch, New Zealand",
    "Dubai, UAE", "Riyadh, Saudi Arabia", "Tel Aviv, Israel", "Doha, Qatar",
    "Kuwait City, Kuwait", "Muscat, Oman", "Manama, Bahrain",
    "Edinburgh, UK", "Manchester, UK", "Birmingham, UK", "Leeds, UK", "Glasgow, UK",
    "Calgary, Canada", "Montreal, Canada", "Ottawa, Canada", "Quebec City, Canada",
    "Perth, Australia", "Brisbane, Australia", "Adelaide, Australia", "Canberra, Australia",
    "",  # Some users don't set location
    "",
]

# Addresses by country (for user.address); subset of _LOCATIONS
_ADDRESSES_BY_COUNTRY: dict[str, list[str]] = {
    "US": ["New York, NY", "San Francisco, CA", "Chicago, IL", "Austin, TX", "Boston, MA", "Seattle, WA", "Denver, CO"],
    "GB": ["London, UK", "Manchester, UK", "Birmingham, UK", "Edinburgh, UK", "Leeds, UK"],
    "DE": ["Berlin, Germany", "Munich, Germany", "Hamburg, Germany", "Cologne, Germany", "Frankfurt, Germany"],
    "FR": ["Paris, France", "Lyon, France", "Marseille, France", "Toulouse, France", "Bordeaux, France"],
    "CA": ["Toronto, Canada", "Vancouver, BC", "Montreal, Canada", "Calgary, Canada", "Ottawa, Canada"],
    "AU": ["Sydney, Australia", "Melbourne, Australia", "Brisbane, Australia", "Perth, Australia", "Adelaide, Australia"],
    "IN": ["Mumbai, India", "Delhi, India", "Bangalore, India", "Chennai, India", "Hyderabad, India"],
    "JP": ["Tokyo, Japan", "Osaka", "Nagoya", "Yokohama", "Kyoto"],
    "BR": ["São Paulo, Brazil", "Rio de Janeiro, Brazil", "Brasília, Brazil", "Salvador, Brazil"],
    "MX": ["Mexico City, Mexico", "Guadalajara, Mexico", "Monterrey, Mexico"],
    "ES": ["Madrid, Spain", "Barcelona, Spain", "Valencia, Spain"],
    "IT": ["Rome, Italy", "Milan, Italy", "Naples, Italy", "Turin, Italy", "Florence, Italy"],
    "NL": ["Amsterdam, Netherlands", "Rotterdam, Netherlands", "The Hague, Netherlands"],
    "RU": ["Moscow, Russia", "Saint Petersburg, Russia"],
    "CN": ["Shanghai, China", "Beijing, China", "Shenzhen, China", "Guangzhou, China"],
    "KR": ["Seoul, South Korea", "Busan, South Korea"],
    "PL": ["Warsaw, Poland", "Kraków, Poland"],
    "SE": ["Stockholm, Sweden"],
    "VN": ["Ho Chi Minh City, Vietnam", "Hanoi, Vietnam"],
    "PH": ["Manila, Philippines", "Cebu City, Philippines"],
    "TR": ["Istanbul, Turkey", "Ankara, Turkey"],
    "NG": ["Lagos, Nigeria", "Abuja, Nigeria"],
    "ZA": ["Cape Town, South Africa", "Johannesburg, South Africa"],
    "ID": ["Jakarta, Indonesia", "Surabaya, Indonesia"],
    "PK": ["Karachi, Pakistan", "Lahore, Pakistan"],
    "TH": ["Bangkok, Thailand"],
    "UA": ["Kyiv, Ukraine"],
    "RO": ["Bucharest, Romania"],
    "BD": ["Dhaka, Bangladesh"],
    "EG": ["Cairo, Egypt"],
}


def _pick_address_for_country(country: str, rng: random.Random) -> str:
    """Return a random address string for the given country."""
    addrs = _ADDRESSES_BY_COUNTRY.get(country)
    if addrs:
        return rng.choice(addrs)
    return ""


# ---------------------------------------------------------------------------
# User agents
# ---------------------------------------------------------------------------
_BROWSER_USER_AGENTS = [
    # Current (2024)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/17.2",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile",
    # Older Chrome / Chromium
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/100.0.4896.127",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/90.0.4430.212",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 Chrome/95.0.4638.69",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/88.0.4324.182",
    # Older Firefox
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:100.0) Gecko/20100101 Firefox/100.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:95.0) Gecko/20100101 Firefox/95.0",
    # Older Safari
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/604.1",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/605.1.15 Safari/605.1.1",
    # Older Edge
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Edg/90.0.818.66",
    # Legacy IE / Edge legacy
    "Mozilla/5.0 (Windows NT 10.0; WOW64; Trident/7.0; rv:11.0) like Gecko",
    # Older mobile
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148",
    "Mozilla/5.0 (Linux; Android 10; SM-G973F) AppleWebKit/537.36 Chrome/91.0.4472.120 Mobile",
    "Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 Chrome/88.0.4324.181 Mobile",
]

_NON_BROWSER_USER_AGENTS = [
    "python-requests/2.31.0",
    "curl/8.4.0",
    "LinkedInApp/9.1.590 (iPhone; iOS 17.2)",
    "LinkedInApp/4.1.940 (Android 14; Pixel 8)",
    "Slackbot-LinkExpanding 1.0 (+https://api.slack.com/robots)",
    "PostmanRuntime/7.35.0",
    "httpie/3.2.2",
    "wget/1.21.4",
    "Go-http-client/2.0",
    "Java/17.0.9",
    "okhttp/4.12.0",
    "node-fetch/3.3.2",
    "axios/1.6.2",
    "Scrapy/2.11.0",
    "Apache-HttpClient/5.3",
]

# ---------------------------------------------------------------------------
# IP generation (first-octet ranges by region, from RIR allocations)
# ---------------------------------------------------------------------------
# ARIN (North America)
_IP_ARIN = [12, 13, 24, 38, 50, 52, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 96, 97, 98, 99, 104, 107, 108]
# RIPE (Europe, Russia, Turkey)
_IP_RIPE = [2, 5, 31, 37, 46, 51, 62, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 109, 141, 144, 146, 176, 178, 185, 188, 193, 194, 195, 212, 213, 217]
# APNIC (Asia-Pacific)
_IP_APNIC = [1, 14, 27, 36, 39, 42, 43, 49, 58, 59, 60, 61, 101, 103, 106, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 123, 124, 125, 126, 133, 139, 140, 150, 153, 157, 163, 171, 175, 180, 182, 183, 202, 203, 210, 211, 218, 219, 220, 221, 222, 223]
# LACNIC (Latin America)
_IP_LACNIC = [138, 143, 168, 170, 177, 179, 181, 186, 187, 189, 191, 200, 201]
# AfriNIC (Africa)
_IP_AFRINIC = [41, 102, 105, 154, 156, 196, 197]

_COUNTRY_IP_FIRST_OCTETS: dict[str, list[int]] = {
    "US": _IP_ARIN,
    "CA": _IP_ARIN,
    "GB": _IP_RIPE,
    "DE": _IP_RIPE,
    "FR": _IP_RIPE,
    "IT": _IP_RIPE,
    "ES": _IP_RIPE,
    "NL": _IP_RIPE,
    "SE": _IP_RIPE,
    "PL": _IP_RIPE,
    "UA": _IP_RIPE,
    "RO": _IP_RIPE,
    "RU": _IP_RIPE,
    "TR": _IP_RIPE,
    "IN": _IP_APNIC,
    "JP": _IP_APNIC,
    "KR": _IP_APNIC,
    "CN": _IP_APNIC,
    "AU": _IP_APNIC,
    "PH": _IP_APNIC,
    "ID": _IP_APNIC,
    "VN": _IP_APNIC,
    "TH": _IP_APNIC,
    "PK": _IP_APNIC,
    "BD": _IP_APNIC,
    "BR": _IP_LACNIC,
    "MX": _IP_LACNIC,
    "NG": _IP_AFRINIC,
    "ZA": _IP_AFRINIC,
    "EG": _IP_AFRINIC,
}


def _random_ip_for_country(country: str, rng: random.Random) -> str:
    """Generate a plausible IP from allocations for the given country."""
    first_octets = _COUNTRY_IP_FIRST_OCTETS.get(country, _IP_ARIN)
    first = rng.choice(first_octets)
    return f"{first}.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"


# ---------------------------------------------------------------------------
# Zipf distribution for connections
# ---------------------------------------------------------------------------
def _zipf_connections(rng: random.Random, config: dict) -> int:
    """
    Sample connections count from a Zipf distribution.

    Most users have few connections; a small number are highly connected.
    zero_connections_pct have zero; the rest use Pareto(alpha=1.2) * 20, capped at 30,000.
    """
    if rng.random() < get_cfg(config, "connections", "zero_connections_pct", default=0.08):
        return 0
    raw = rng.paretovariate(1.2)
    return min(int(raw * 20), 30_000)


# ---------------------------------------------------------------------------
# Email generation (name-based, varied formats and domains)
# ---------------------------------------------------------------------------
def _ascii_local(s: str) -> str:
    """Normalize name for email local part (replace accented chars)."""
    replacements = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "æ": "ae", "ø": "o"}
    out = s.lower()
    for old, new in replacements.items():
        out = out.replace(old, new)
    return out


def _make_random_email(rng: random.Random, used_emails: set[str]) -> str:
    """Generate unique email unrelated to display name (e.g. work, old, or generic)."""
    domain = rng.choices(_EMAIL_DOMAINS, weights=_EMAIL_DOMAIN_WEIGHTS, k=1)[0]
    prefixes = ("user", "contact", "hello", "info", "mail", "box", "id", "acc")
    local = f"{rng.choice(prefixes)}{rng.randint(1000, 999999)}"
    email = f"{local}@{domain}"
    while email in used_emails:
        local = f"{rng.choice(prefixes)}{rng.randint(10000, 99999999)}"
        email = f"{local}@{domain}"
    used_emails.add(email)
    return email


def _make_email(
    first: str,
    last: str,
    rng: random.Random,
    used_emails: set[str],
    config: dict,
) -> str:
    """Generate unique email from name; mostly first.last with some variations."""
    f, l = _ascii_local(first), _ascii_local(last)
    domain = rng.choices(_EMAIL_DOMAINS, weights=_EMAIL_DOMAIN_WEIGHTS, k=1)[0]
    suffix = (
        str(rng.randint(1, 9999))
        if rng.random() < get_cfg(config, "email", "suffix_pct", default=0.35)
        else ""
    )

    roll = rng.random()
    t1 = get_cfg(config, "email", "first_last", default=0.70)
    t2 = get_cfg(config, "email", "firstlast", default=0.85)
    t3 = get_cfg(config, "email", "last_first", default=0.92)
    if roll < t1:
        local = f"{f}.{l}{suffix}"
    elif roll < t2:
        local = f"{f}{l}{suffix}" if suffix else f"{f}.{l}"
    elif roll < t3:
        local = f"{l}.{f}{suffix}"
    else:
        local = f"{f}_{l}{suffix}"

    email = f"{local}@{domain}"
    while email in used_emails:
        suffix = str(rng.randint(1, 99999))
        local = f"{f}.{l}{suffix}"
        email = f"{local}@{domain}"
    used_emails.add(email)
    return email


# ---------------------------------------------------------------------------
# User generation
# ---------------------------------------------------------------------------
def _generate_users(
    rng: random.Random,
    now: datetime,
    num_users: int = NUM_USERS,
    config: dict | None = None,
) -> tuple[list[User], set[str], dict[str, tuple[str, str]]]:
    """Generate num_users users with realistic distributions."""
    cfg = config or {}
    users: list[User] = []
    used_emails: set[str] = set()
    name_map: dict[str, tuple[str, str]] = {}

    move_pct = get_cfg(cfg, "users", "move_pct", default=0.04)

    for i in range(num_users):
        user_id = f"u-{i:06d}"
        registration_country = rng.choices(_COUNTRIES, weights=_COUNTRY_W, k=1)[0]
        languages = _COUNTRY_LANG.get(registration_country, ("en",))
        language = rng.choice(languages)

        # Small fraction of users "move" to another country; legit activity uses new-country IPs
        moved = rng.random() < move_pct
        if moved:
            other_countries = [c for c in _COUNTRIES if c != registration_country]
            if other_countries:
                country = rng.choice(other_countries)
                languages = _COUNTRY_LANG.get(country, ("en",))
                language = rng.choice(languages)
            else:
                country = registration_country
                moved = False
        else:
            country = registration_country

        is_hosting = rng.random() < get_cfg(cfg, "users", "hosting_ip_pct", default=0.10)
        ip_type = IPType.HOSTING if is_hosting else IPType.RESIDENTIAL
        registration_ip = _random_ip_for_country(registration_country, rng)
        ip_address = _random_ip_for_country(country, rng)
        address = _pick_address_for_country(country, rng)

        days_ago = rng.randint(1, 730)
        join_date = now - timedelta(days=days_ago, seconds=rng.randint(0, 86400))

        first_names, last_names, _, _ = _get_content_for_lang(language)
        first = rng.choice(first_names)
        last = rng.choice(last_names)
        name_map[user_id] = (first, last)
        email = (
            _make_random_email(rng, used_emails)
            if rng.random() < get_cfg(cfg, "users", "unrelated_email_pct", default=0.05)
            else _make_email(first, last, rng, used_emails, cfg)
        )

        inactive_pct = get_cfg(cfg, "users", "inactive_pct", default=0.05)
        is_active = rng.random() >= inactive_pct

        email_verified = rng.random() < get_cfg(cfg, "users", "email_verified_pct", default=0.95)
        two_factor_enabled = rng.random() < get_cfg(cfg, "users", "two_factor_pct", default=0.25)
        phone_verified = rng.random() < get_cfg(cfg, "users", "phone_verified_pct", default=0.60)

        last_password_change_at = None
        if rng.random() < get_cfg(cfg, "users", "password_changed_pct", default=0.40):
            delta_max = (now - join_date).total_seconds()
            delta_sec = rng.randint(0, max(0, int(delta_max)))
            last_password_change_at = join_date + timedelta(seconds=delta_sec)

        tier_roll = rng.random()
        free_pct = get_cfg(cfg, "users", "account_tier_free", default=0.70)
        prem_pct = get_cfg(cfg, "users", "account_tier_premium", default=0.25)
        if tier_roll < free_pct:
            account_tier = "free"
        elif tier_roll < free_pct + prem_pct:
            account_tier = "premium"
        else:
            account_tier = "enterprise"

        user_type = "recruiter" if rng.random() < get_cfg(cfg, "users", "recruiter_pct", default=0.06) else "regular"

        failed_login_streak = 0
        if rng.random() < get_cfg(cfg, "users", "failed_login_streak_pct", default=0.05):
            failed_login_streak = rng.randint(1, 3)

        users.append(User(
            user_id=user_id,
            email=email,
            join_date=join_date,
            country=country,
            ip_address=ip_address,
            registration_ip=registration_ip,
            registration_country=registration_country,
            address=address,
            ip_type=ip_type,
            language=language,
            is_active=is_active,
            generation_pattern=GENERATION_PATTERN_CLEAN,
            email_verified=email_verified,
            two_factor_enabled=two_factor_enabled,
            last_password_change_at=last_password_change_at,
            account_tier=account_tier,
            failed_login_streak=failed_login_streak,
            phone_verified=phone_verified,
            user_type=user_type,
        ))

    return users, used_emails, name_map


def _fishy_counts(config: dict | None) -> tuple[int, int, int, int, int, int]:
    """Return (num_fake, num_pharmacy, num_covert_porn, num_account_farming, num_harassment, num_like_inflation)."""
    cfg = config or {}
    return (
        get_cfg(cfg, "fishy_accounts", "num_fake", default=NUM_FAKE_ACCOUNTS),
        get_cfg(cfg, "fishy_accounts", "num_pharmacy", default=NUM_PHARMACY_ACCOUNTS),
        get_cfg(cfg, "fishy_accounts", "num_covert_porn", default=NUM_COVERT_PORN_ACCOUNTS),
        get_cfg(cfg, "fishy_accounts", "num_account_farming", default=NUM_ACCOUNT_FARMING_ACCOUNTS),
        get_cfg(cfg, "fishy_accounts", "num_harassment", default=NUM_HARASSMENT_ACCOUNTS),
        get_cfg(cfg, "fishy_accounts", "num_like_inflation", default=NUM_LIKE_INFLATION_ACCOUNTS),
    )


# Legacy exports: use config-based counts when available; these are fallbacks for tests.
FAKE_ACCOUNT_USER_IDS: list[str] = [
    f"u-{NUM_USERS + i:06d}" for i in range(NUM_FAKE_ACCOUNTS)
]
PHARMACY_ACCOUNT_USER_IDS: list[str] = [
    f"u-{NUM_USERS + NUM_FAKE_ACCOUNTS + i:06d}" for i in range(NUM_PHARMACY_ACCOUNTS)
]
COVERT_PORN_ACCOUNT_USER_IDS: list[str] = [
    f"u-{NUM_USERS + NUM_FAKE_ACCOUNTS + NUM_PHARMACY_ACCOUNTS + i:06d}"
    for i in range(NUM_COVERT_PORN_ACCOUNTS)
]
ACCOUNT_FARMING_USER_IDS: list[str] = [
    f"u-{NUM_USERS + NUM_FAKE_ACCOUNTS + NUM_PHARMACY_ACCOUNTS + NUM_COVERT_PORN_ACCOUNTS + i:06d}"
    for i in range(NUM_ACCOUNT_FARMING_ACCOUNTS)
]
HARASSMENT_ACCOUNT_USER_IDS: list[str] = [
    f"u-{NUM_USERS + NUM_FAKE_ACCOUNTS + NUM_PHARMACY_ACCOUNTS + NUM_COVERT_PORN_ACCOUNTS + NUM_ACCOUNT_FARMING_ACCOUNTS + i:06d}"
    for i in range(NUM_HARASSMENT_ACCOUNTS)
]
LIKE_INFLATION_ACCOUNT_USER_IDS: list[str] = [
    f"u-{NUM_USERS + NUM_FAKE_ACCOUNTS + NUM_PHARMACY_ACCOUNTS + NUM_COVERT_PORN_ACCOUNTS + NUM_ACCOUNT_FARMING_ACCOUNTS + NUM_HARASSMENT_ACCOUNTS + i:06d}"
    for i in range(NUM_LIKE_INFLATION_ACCOUNTS)
]


# ---------------------------------------------------------------------------
# Fake account users (for fake_account attack pattern)
# ---------------------------------------------------------------------------
def _generate_fake_account_users(
    rng: random.Random,
    now: datetime,
    used_emails: set[str],
    base_idx: int,
    count: int,
) -> tuple[list[User], dict[str, tuple[str, str]]]:
    """
    Generate fake account users. These are created by IP rings (shared IPs
    from one country). They get only ACCOUNT_CREATION in mock_data; the
    rest of the attack flow is added by fraud.
    """
    users: list[User] = []
    name_map: dict[str, tuple[str, str]] = {}

    for i in range(count):
        user_id = f"u-{base_idx + i:06d}"
        country = "RU"  # Fake accounts appear to originate from RU
        language = "ru"

        # Join date: 50-55 days ago (dormant for a while)
        days_ago = rng.randint(50, 55)
        join_date = now - timedelta(days=days_ago, seconds=rng.randint(0, 86400))

        first = rng.choice(_FIRST_NAMES)
        last = rng.choice(_LAST_NAMES)
        name_map[user_id] = (first, last)
        f, l = _ascii_local(first), _ascii_local(last)
        local = f"fake{base_idx}.{f}.{l}{rng.randint(1, 9999)}"
        domain = rng.choices(_EMAIL_DOMAINS, weights=_EMAIL_DOMAIN_WEIGHTS, k=1)[0]
        email = f"{local}@{domain}"
        while email in used_emails:
            local = f"fake{base_idx}.{f}.{l}{rng.randint(1, 99999)}"
            email = f"{local}@{domain}"
        used_emails.add(email)

        # Fake accounts are "active" until malicious flow closes them
        ip_address = rng.choice(_FAKE_ACCOUNT_IP_POOL_RU)
        ip_type = IPType.RESIDENTIAL

        users.append(User(
            user_id=user_id,
            email=email,
            join_date=join_date,
            country=country,
            ip_address=ip_address,
            registration_ip=ip_address,
            registration_country=country,
            address="",
            ip_type=ip_type,
            language=language,
            is_active=True,
            generation_pattern="fake_account",
            email_verified=False,       # Fake accounts skip verification
            two_factor_enabled=False,
            last_password_change_at=None,
            account_tier="free",
            failed_login_streak=0,
            phone_verified=False,       # Fake accounts never verify phone
        ))

    return users, name_map


# ---------------------------------------------------------------------------
# Pharmacy phishing users (fishy profiles for foreign drug fronts)
# ---------------------------------------------------------------------------
def _generate_pharmacy_users(
    rng: random.Random,
    now: datetime,
    used_emails: set[str],
    base_idx: int,
    count: int,
    config: dict | None = None,
) -> tuple[list[User], dict[str, tuple[str, str]]]:
    """
    Generate pharmacy phishing users. These are fronts for foreign "pharmacies"
    selling drugs under covert names. Profiles contain links to websites in
    various countries and street names for drugs. Labeled pharmacy_phishing.
    """
    cfg = config or {}
    hosting_pct = get_cfg(cfg, "fishy_accounts", "pharmacy", "hosting_ip_pct", default=0.15)
    email_verified_pct = get_cfg(cfg, "fishy_accounts", "pharmacy", "email_verified_pct", default=0.3)

    users: list[User] = []
    name_map: dict[str, tuple[str, str]] = {}

    # Pharmacy accounts originate from various countries (common for this type)
    pharmacy_countries = ["IN", "MX", "RU", "TR", "PH", "PK", "TH", "VN", "GB", "CA"]
    pharmacy_country_weights = [4, 3, 3, 2, 2, 2, 2, 1, 1, 1]

    for i in range(count):
        user_id = f"u-{base_idx + i:06d}"
        country = rng.choices(pharmacy_countries, weights=pharmacy_country_weights, k=1)[0]
        language = "en" if country in ("US", "GB", "CA", "IN", "PH", "PK", "NG") else "en"

        days_ago = rng.randint(14, 45)
        join_date = now - timedelta(days=days_ago, seconds=rng.randint(0, 86400))

        first = rng.choice(_FIRST_NAMES)
        last = rng.choice(_LAST_NAMES)
        name_map[user_id] = (first, last)
        f, l = _ascii_local(first), _ascii_local(last)
        local = f"pharma{base_idx}.{f}.{l}{rng.randint(1, 9999)}"
        domain = rng.choices(_EMAIL_DOMAINS, weights=_EMAIL_DOMAIN_WEIGHTS, k=1)[0]
        email = f"{local}@{domain}"
        while email in used_emails:
            local = f"pharma{base_idx}.{f}.{l}{rng.randint(1, 99999)}"
            email = f"{local}@{domain}"
        used_emails.add(email)

        is_hosting = rng.random() < hosting_pct
        ip_type = IPType.HOSTING if is_hosting else IPType.RESIDENTIAL
        ip_address = _random_ip_for_country(country, rng)

        users.append(User(
            user_id=user_id,
            email=email,
            join_date=join_date,
            country=country,
            ip_address=ip_address,
            registration_ip=ip_address,
            registration_country=country,
            address="",
            ip_type=ip_type,
            language=language,
            is_active=True,
            generation_pattern="pharmacy_phishing",
            email_verified=rng.random() < email_verified_pct,
            two_factor_enabled=False,
            last_password_change_at=None,
            account_tier="free",
            failed_login_streak=0,
            phone_verified=False,
        ))

    return users, name_map


# ---------------------------------------------------------------------------
# Covert porn users (fishy profiles for adult content fronts)
# ---------------------------------------------------------------------------
def _generate_covert_porn_users(
    rng: random.Random,
    now: datetime,
    used_emails: set[str],
    base_idx: int,
    count: int,
    config: dict | None = None,
) -> tuple[list[User], dict[str, tuple[str, str]]]:
    """
    Generate covert porn users. Fronts for adult content using euphemistic
    headlines and links to various sites. Labeled covert_porn.
    """
    cfg = config or {}
    hosting_pct = get_cfg(cfg, "fishy_accounts", "covert_porn", "hosting_ip_pct", default=0.2)
    email_verified_pct = get_cfg(cfg, "fishy_accounts", "covert_porn", "email_verified_pct", default=0.4)

    users: list[User] = []
    name_map: dict[str, tuple[str, str]] = {}

    porn_countries = ["US", "GB", "MX", "RU", "NL", "PH", "TH", "BR", "CA", "DE"]
    porn_country_weights = [4, 3, 3, 2, 2, 2, 2, 1, 1, 1]

    for i in range(count):
        user_id = f"u-{base_idx + i:06d}"
        country = rng.choices(porn_countries, weights=porn_country_weights, k=1)[0]
        language = "en"

        days_ago = rng.randint(10, 40)
        join_date = now - timedelta(days=days_ago, seconds=rng.randint(0, 86400))

        first = rng.choice(_FIRST_NAMES)
        last = rng.choice(_LAST_NAMES)
        name_map[user_id] = (first, last)
        f, l = _ascii_local(first), _ascii_local(last)
        local = f"creator{base_idx}.{f}.{l}{rng.randint(1, 9999)}"
        domain = rng.choices(_EMAIL_DOMAINS, weights=_EMAIL_DOMAIN_WEIGHTS, k=1)[0]
        email = f"{local}@{domain}"
        while email in used_emails:
            local = f"creator{base_idx}.{f}.{l}{rng.randint(1, 99999)}"
            email = f"{local}@{domain}"
        used_emails.add(email)

        is_hosting = rng.random() < hosting_pct
        ip_type = IPType.HOSTING if is_hosting else IPType.RESIDENTIAL
        ip_address = _random_ip_for_country(country, rng)

        users.append(User(
            user_id=user_id,
            email=email,
            join_date=join_date,
            country=country,
            ip_address=ip_address,
            registration_ip=ip_address,
            registration_country=country,
            address="",
            ip_type=ip_type,
            language=language,
            is_active=True,
            generation_pattern="covert_porn",
            email_verified=rng.random() < email_verified_pct,
            two_factor_enabled=False,
            last_password_change_at=None,
            account_tier="free",
            failed_login_streak=0,
            phone_verified=False,
        ))

    return users, name_map


def _generate_account_farming_users(
    rng: random.Random,
    now: datetime,
    used_emails: set[str],
    base_idx: int,
    count: int,
) -> tuple[list[User], dict[str, tuple[str, str]]]:
    """Accounts created by hosting IP clusters, sold to buyers who take over."""
    users: list[User] = []
    name_map: dict[str, tuple[str, str]] = {}

    for i in range(count):
        user_id = f"u-{base_idx + i:06d}"
        country = "US"
        language = "en"
        days_ago = rng.randint(20, 45)
        join_date = now - timedelta(days=days_ago, seconds=rng.randint(0, 86400))

        first, last = rng.choice(_FIRST_NAMES), rng.choice(_LAST_NAMES)
        name_map[user_id] = (first, last)
        f, l = _ascii_local(first), _ascii_local(last)
        local = f"farm{base_idx}.{f}.{l}{rng.randint(1, 9999)}"
        domain = rng.choices(_EMAIL_DOMAINS, weights=_EMAIL_DOMAIN_WEIGHTS, k=1)[0]
        email = f"{local}@{domain}"
        while email in used_emails:
            local = f"farm{base_idx}.{f}.{l}{rng.randint(1, 99999)}"
            email = f"{local}@{domain}"
        used_emails.add(email)

        ip_address = rng.choice(_FAKE_ACCOUNT_IP_POOL_RU)
        ip_type = IPType.HOSTING

        users.append(User(
            user_id=user_id,
            email=email,
            join_date=join_date,
            country=country,
            ip_address=ip_address,
            registration_ip=ip_address,
            registration_country=country,
            address="",
            ip_type=ip_type,
            language=language,
            is_active=True,
            generation_pattern="account_farming",
            email_verified=False,
            two_factor_enabled=False,
            last_password_change_at=None,
            account_tier="free",
            failed_login_streak=0,
            phone_verified=False,
        ))

    return users, name_map


def _generate_harassment_users(
    rng: random.Random,
    now: datetime,
    used_emails: set[str],
    base_idx: int,
    count: int,
) -> tuple[list[User], dict[str, tuple[str, str]]]:
    """Fake accounts for coordinated harassment."""
    users: list[User] = []
    name_map: dict[str, tuple[str, str]] = {}

    for i in range(count):
        user_id = f"u-{base_idx + i:06d}"
        country = "RU"
        language = "en"
        days_ago = rng.randint(30, 50)
        join_date = now - timedelta(days=days_ago, seconds=rng.randint(0, 86400))

        first, last = rng.choice(_FIRST_NAMES), rng.choice(_LAST_NAMES)
        name_map[user_id] = (first, last)
        f, l = _ascii_local(first), _ascii_local(last)
        local = f"harass{base_idx}.{f}.{l}{rng.randint(1, 9999)}"
        domain = rng.choices(_EMAIL_DOMAINS, weights=_EMAIL_DOMAIN_WEIGHTS, k=1)[0]
        email = f"{local}@{domain}"
        while email in used_emails:
            local = f"harass{base_idx}.{f}.{l}{rng.randint(1, 99999)}"
            email = f"{local}@{domain}"
        used_emails.add(email)

        ip_address = rng.choice(_FAKE_ACCOUNT_IP_POOL_RU)
        ip_type = IPType.HOSTING

        users.append(User(
            user_id=user_id,
            email=email,
            join_date=join_date,
            country=country,
            ip_address=ip_address,
            registration_ip=ip_address,
            registration_country=country,
            address="",
            ip_type=ip_type,
            language=language,
            is_active=True,
            generation_pattern="coordinated_harassment",
            email_verified=False,
            two_factor_enabled=False,
            last_password_change_at=None,
            account_tier="free",
            failed_login_streak=0,
            phone_verified=False,
        ))

    return users, name_map


def _generate_like_inflation_users(
    rng: random.Random,
    now: datetime,
    used_emails: set[str],
    base_idx: int,
    count: int,
) -> tuple[list[User], dict[str, tuple[str, str]]]:
    """Fake accounts for coordinated like inflation."""
    users: list[User] = []
    name_map: dict[str, tuple[str, str]] = {}

    for i in range(count):
        user_id = f"u-{base_idx + i:06d}"
        country = "RU"
        language = "en"
        days_ago = rng.randint(25, 48)
        join_date = now - timedelta(days=days_ago, seconds=rng.randint(0, 86400))

        first, last = rng.choice(_FIRST_NAMES), rng.choice(_LAST_NAMES)
        name_map[user_id] = (first, last)
        f, l = _ascii_local(first), _ascii_local(last)
        local = f"like{base_idx}.{f}.{l}{rng.randint(1, 9999)}"
        domain = rng.choices(_EMAIL_DOMAINS, weights=_EMAIL_DOMAIN_WEIGHTS, k=1)[0]
        email = f"{local}@{domain}"
        while email in used_emails:
            local = f"like{base_idx}.{f}.{l}{rng.randint(1, 99999)}"
            email = f"{local}@{domain}"
        used_emails.add(email)

        ip_address = rng.choice(_FAKE_ACCOUNT_IP_POOL_RU)
        ip_type = IPType.HOSTING

        users.append(User(
            user_id=user_id,
            email=email,
            join_date=join_date,
            country=country,
            ip_address=ip_address,
            registration_ip=ip_address,
            registration_country=country,
            address="",
            ip_type=ip_type,
            language=language,
            is_active=True,
            generation_pattern="coordinated_like_inflation",
            email_verified=False,
            two_factor_enabled=False,
            last_password_change_at=None,
            account_tier="free",
            failed_login_streak=0,
            phone_verified=False,
        ))

    return users, name_map


# ---------------------------------------------------------------------------
# Profile generation
# ---------------------------------------------------------------------------
def _generate_profiles(
    users: list[User],
    name_map: dict[str, tuple[str, str]],
    rng: random.Random,
    now: datetime,
    config: dict | None = None,
) -> list[UserProfile]:
    """Generate a UserProfile for every user with Zipf-distributed connections."""
    cfg = config or {}
    profiles: list[UserProfile] = []
    fake_ids = {u.user_id for u in users if getattr(u, "generation_pattern", "") == "fake_account"}
    is_pharmacy = lambda u: getattr(u, "generation_pattern", "") == "pharmacy_phishing"
    is_covert_porn = lambda u: getattr(u, "generation_pattern", "") == "covert_porn"
    is_account_farming = lambda u: getattr(u, "generation_pattern", "") == "account_farming"
    is_harassment = lambda u: getattr(u, "generation_pattern", "") == "coordinated_harassment"
    is_like_inflation = lambda u: getattr(u, "generation_pattern", "") == "coordinated_like_inflation"

    for user in users:
        is_fake = user.user_id in fake_ids
        is_pharm = is_pharmacy(user)
        is_porn = is_covert_porn(user)
        is_farming = is_account_farming(user)
        is_harass = is_harassment(user)
        is_like = is_like_inflation(user)
        first, last = name_map.get(user.user_id, (rng.choice(_FIRST_NAMES), rng.choice(_LAST_NAMES)))
        display_name = f"{first} {last}"

        if is_pharm:
            headline = rng.choice(_PHARMACY_HEADLINES)
            url = rng.choice(_PHARMACY_WEBSITES)
            summary = rng.choice(_PHARMACY_SUMMARIES).format(url=url)
        elif is_porn:
            headline = rng.choice(_PORN_HEADLINES)
            url = rng.choice(_PORN_WEBSITES)
            summary = rng.choice(_PORN_SUMMARIES).format(url=url)
        elif is_farming:
            headline = rng.choice(_FARMING_HEADLINES)
            summary = rng.choice(_FARMING_SUMMARIES)
        elif is_harass or is_like:
            headline = rng.choice(_HEADLINES)
            summary = rng.choice(_SUMMARIES)
        else:
            # Genuine user: align headline and summary with user language
            _, _, headlines, summaries = _get_content_for_lang(user.language)
            headline = rng.choice(headlines)
            summary = rng.choice(summaries)

        connections_count = _zipf_connections(rng, cfg)

        # Profile created shortly after join
        profile_offset = timedelta(seconds=rng.randint(60, 3600))
        profile_created_at = user.join_date + profile_offset
        if profile_created_at > now:
            profile_created_at = now - timedelta(seconds=1)

        last_updated_at = None
        if rng.random() < get_cfg(cfg, "profiles", "profile_updated_pct", default=0.70):
            update_offset = timedelta(
                days=rng.randint(1, max(1, (now - profile_created_at).days or 1))
            )
            last_updated_at = profile_created_at + update_offset
            if last_updated_at > now:
                last_updated_at = now - timedelta(seconds=1)

        # --- New profile fields ---
        if is_fake:
            # Fake accounts: minimal profiles
            has_profile_photo = False
            location_text = ""
            endorsements_count = 0
            profile_views_received = rng.randint(0, 5)
        elif is_pharm:
            # Pharmacy fronts: plausible-looking but minimal engagement
            has_photo_pct = get_cfg(cfg, "fishy_accounts", "profiles", "pharmacy_has_photo_pct", default=0.4)
            location_pct = get_cfg(cfg, "fishy_accounts", "profiles", "pharmacy_location_pct", default=0.6)
            endorsements_max = get_cfg(cfg, "fishy_accounts", "profiles", "pharmacy_endorsements_max", default=3)
            has_profile_photo = rng.random() < has_photo_pct
            location_text = rng.choice(_LOCATIONS) if rng.random() < location_pct else ""
            endorsements_count = rng.randint(0, endorsements_max)
            profile_views_received = rng.randint(5, 50)
        elif is_porn:
            # Covert porn fronts: plausible-looking, minimal engagement
            has_photo_pct = get_cfg(cfg, "fishy_accounts", "profiles", "covert_porn_has_photo_pct", default=0.5)
            location_pct = get_cfg(cfg, "fishy_accounts", "profiles", "covert_porn_location_pct", default=0.5)
            endorsements_max = get_cfg(cfg, "fishy_accounts", "profiles", "covert_porn_endorsements_max", default=2)
            has_profile_photo = rng.random() < has_photo_pct
            location_text = rng.choice(_LOCATIONS) if rng.random() < location_pct else ""
            endorsements_count = rng.randint(0, endorsements_max)
            profile_views_received = rng.randint(5, 80)
        elif is_farming:
            has_photo_pct = get_cfg(cfg, "fishy_accounts", "profiles", "farming_has_photo_pct", default=0.3)
            location_pct = get_cfg(cfg, "fishy_accounts", "profiles", "farming_location_pct", default=0.5)
            endorsements_max = get_cfg(cfg, "fishy_accounts", "profiles", "farming_endorsements_max", default=2)
            has_profile_photo = rng.random() < has_photo_pct
            location_text = rng.choice(_LOCATIONS) if rng.random() < location_pct else ""
            endorsements_count = rng.randint(0, endorsements_max)
            profile_views_received = rng.randint(0, 20)
        elif is_harass:
            has_photo_pct = get_cfg(cfg, "fishy_accounts", "profiles", "harassment_has_photo_pct", default=0.3)
            has_profile_photo = rng.random() < has_photo_pct
            location_text = ""
        elif is_like:
            has_photo_pct = get_cfg(cfg, "fishy_accounts", "profiles", "like_inflation_has_photo_pct", default=0.3)
            has_profile_photo = rng.random() < has_photo_pct
            location_text = ""
            endorsements_count = 0
            profile_views_received = rng.randint(0, 10)
        else:
            has_profile_photo = rng.random() < get_cfg(cfg, "profiles", "profile_photo_pct", default=0.75)
            location_text = rng.choice(_LOCATIONS)
            # Endorsements: Zipf-like, loosely correlated with connections
            endorsements_count = min(int(rng.paretovariate(1.5) * 3), connections_count)
            # Profile views: Zipf-like
            profile_views_received = min(int(rng.paretovariate(1.1) * 10), 50_000)

        # Profile completeness: fraction of key fields that are filled
        filled = sum([
            bool(display_name),
            bool(headline),
            bool(summary),
            has_profile_photo,
            bool(location_text),
        ])
        profile_completeness = round(filled / 5.0, 2)

        profiles.append(UserProfile(
            user_id=user.user_id,
            display_name=display_name,
            headline=headline,
            summary=summary,
            connections_count=connections_count,
            profile_created_at=profile_created_at,
            last_updated_at=last_updated_at,
            has_profile_photo=has_profile_photo,
            profile_completeness=profile_completeness,
            endorsements_count=endorsements_count,
            profile_views_received=profile_views_received,
            location_text=location_text,
        ))

    return profiles


# ---------------------------------------------------------------------------
# Interaction generation
# ---------------------------------------------------------------------------


def _generate_interactions(
    users: list[User],
    rng: random.Random,
    now: datetime,
    config: dict | None = None,
) -> list[UserInteraction]:
    """
    Generate up to 2 months of interactions for all users.

    - Fake accounts: ACCOUNT_CREATION only (from shared IP pool).
    - Pharmacy phishing accounts: ACCOUNT_CREATION only (minimal activity).
    - Covert porn accounts: ACCOUNT_CREATION only (minimal activity).
    - Account farming, harassment, like inflation: ACCOUNT_CREATION from hosting.
    - Legitimate users: pattern-based generation via non_fraud module.
      Respects temporal invariants: ACCOUNT_CREATION first, LOGIN before
      other activity, VIEW before MESSAGE/CONNECT when reaching out.
    - Inactive users get a CLOSE_ACCOUNT event (terminal).
    """
    cfg = config or {}
    interactions: list[UserInteraction] = []
    all_user_ids = [u.user_id for u in users]
    window_start = now - timedelta(days=INTERACTION_WINDOW_DAYS)

    interaction_counter = 0

    user_primary_ua: dict[str, str] = {}
    for user in users:
        if rng.random() < get_cfg(cfg, "user_agents", "non_browser_ua_pct", default=0.12):
            user_primary_ua[user.user_id] = rng.choice(_NON_BROWSER_USER_AGENTS)
        else:
            user_primary_ua[user.user_id] = rng.choice(_BROWSER_USER_AGENTS)

    fake_ids = {u.user_id for u in users if getattr(u, "generation_pattern", "") == "fake_account"}
    pharmacy_ids = {u.user_id for u in users if getattr(u, "generation_pattern", "") == "pharmacy_phishing"}
    porn_ids = {u.user_id for u in users if getattr(u, "generation_pattern", "") == "covert_porn"}
    farming_ids = {u.user_id for u in users if getattr(u, "generation_pattern", "") == "account_farming"}
    harass_ids = {u.user_id for u in users if getattr(u, "generation_pattern", "") == "coordinated_harassment"}
    like_ids = {u.user_id for u in users if getattr(u, "generation_pattern", "") == "coordinated_like_inflation"}
    excluded_ids = fake_ids | pharmacy_ids | porn_ids | farming_ids | harass_ids | like_ids

    # Fake accounts: ACCOUNT_CREATION only
    for user in users:
        if user.user_id not in fake_ids:
            continue
        primary_ua = user_primary_ua.get(user.user_id, rng.choice(_BROWSER_USER_AGENTS))
        interaction_counter += 1
        create_ts = user.join_date
        if create_ts < window_start:
            create_ts = window_start
        ip = rng.choice(_FAKE_ACCOUNT_IP_POOL_RU)
        interactions.append(UserInteraction(
            interaction_id=f"evt-{interaction_counter:08d}",
            user_id=user.user_id,
            interaction_type=InteractionType.ACCOUNT_CREATION,
            timestamp=create_ts,
            ip_address=ip,
            ip_type=IPType.RESIDENTIAL,
            metadata={"user_agent": primary_ua, "ip_country": "RU"},
        ))

    # Pharmacy phishing accounts: ACCOUNT_CREATION only (use their own IP)
    for user in users:
        if user.user_id not in pharmacy_ids:
            continue
        primary_ua = user_primary_ua.get(user.user_id, rng.choice(_BROWSER_USER_AGENTS))
        interaction_counter += 1
        create_ts = user.join_date
        if create_ts < window_start:
            create_ts = window_start
        interactions.append(UserInteraction(
            interaction_id=f"evt-{interaction_counter:08d}",
            user_id=user.user_id,
            interaction_type=InteractionType.ACCOUNT_CREATION,
            timestamp=create_ts,
            ip_address=user.registration_ip,
            ip_type=user.ip_type,
            metadata={"user_agent": primary_ua, "ip_country": user.registration_country},
        ))

    # Covert porn accounts: ACCOUNT_CREATION only (use their own IP)
    for user in users:
        if user.user_id not in porn_ids:
            continue
        primary_ua = user_primary_ua.get(user.user_id, rng.choice(_BROWSER_USER_AGENTS))
        interaction_counter += 1
        create_ts = user.join_date
        if create_ts < window_start:
            create_ts = window_start
        interactions.append(UserInteraction(
            interaction_id=f"evt-{interaction_counter:08d}",
            user_id=user.user_id,
            interaction_type=InteractionType.ACCOUNT_CREATION,
            timestamp=create_ts,
            ip_address=user.registration_ip,
            ip_type=user.ip_type,
            metadata={"user_agent": primary_ua, "ip_country": user.registration_country},
        ))

    # Account farming, harassment, like inflation: ACCOUNT_CREATION from hosting cluster
    for user in users:
        if user.user_id not in (farming_ids | harass_ids | like_ids):
            continue
        primary_ua = user_primary_ua.get(user.user_id, rng.choice(_BROWSER_USER_AGENTS))
        interaction_counter += 1
        create_ts = user.join_date
        if create_ts < window_start:
            create_ts = window_start
        ip = rng.choice(_FAKE_ACCOUNT_IP_POOL_RU)
        interactions.append(UserInteraction(
            interaction_id=f"evt-{interaction_counter:08d}",
            user_id=user.user_id,
            interaction_type=InteractionType.ACCOUNT_CREATION,
            timestamp=create_ts,
            ip_address=ip,
            ip_type=IPType.HOSTING,
            metadata={"user_agent": primary_ua, "ip_country": "RU", "ip_cluster": True},
        ))

    _last_pct = [-1]

    def _progress(processed: int, total: int, events_count: int) -> None:
        if total <= 0:
            return
        pct = 100 * processed / total
        if processed == 1 or processed == total or pct >= _last_pct[0] + 5:
            _last_pct[0] = int(pct // 5) * 5
            print(f"\r  Users: {processed:,}/{total:,} ({pct:.1f}%) | Events: {events_count:,}", end="", flush=True)

    legit_events, interaction_counter = generate_legitimate_events(
        users, all_user_ids, window_start, now,
        interaction_counter, rng, user_primary_ua, excluded_ids,
        config=cfg,
        progress_callback=_progress,
    )
    if len(users) > len(excluded_ids):
        print()
    interactions.extend(legit_events)

    # Sort by timestamp for realism
    interactions.sort(key=lambda i: i.timestamp)

    # Enforce invariant: account creation must be first per user,
    # and no events after CLOSE_ACCOUNT.
    interactions = _enforce_account_creation_first(interactions)
    interactions = _enforce_close_account_invariant(interactions)

    # Assign session IDs based on temporal gaps and login events
    _assign_session_ids(interactions, prefix="s")

    return interactions


def _assign_session_ids(
    interactions: list[UserInteraction],
    prefix: str = "s",
) -> None:
    """
    Assign session_id to interactions IN PLACE (mutates frozen instances).

    A new session starts when:
      - It's the first event for a user.
      - The event is a LOGIN or ACCOUNT_CREATION.
      - There's a 30+ minute gap since the previous event for that user.

    Must be called after sorting by timestamp.
    Uses object.__setattr__ to bypass frozen dataclass restriction.
    """
    user_session_counter: dict[str, int] = {}
    user_last_ts: dict[str, datetime] = {}
    session_gap = timedelta(minutes=30)

    for interaction in interactions:
        uid = interaction.user_id
        ts = interaction.timestamp
        itype = interaction.interaction_type

        new_session = False
        if uid not in user_session_counter:
            new_session = True
        elif itype in (InteractionType.LOGIN, InteractionType.ACCOUNT_CREATION):
            new_session = True
        elif (ts - user_last_ts[uid]) > session_gap:
            new_session = True

        if new_session:
            user_session_counter[uid] = user_session_counter.get(uid, 0) + 1

        user_last_ts[uid] = ts
        session_id = f"{uid}-{prefix}{user_session_counter[uid]:04d}"
        object.__setattr__(interaction, "session_id", session_id)


def _enforce_account_creation_first(
    interactions: list[UserInteraction],
) -> list[UserInteraction]:
    """
    Ensure ACCOUNT_CREATION is the first event per user.
    Move any events timestamped before account creation to after it.
    Input must be sorted by timestamp.
    """
    creation_ts: dict[str, datetime] = {}

    # First pass: find creation timestamps
    for i in interactions:
        if i.interaction_type == InteractionType.ACCOUNT_CREATION:
            if i.user_id not in creation_ts:
                creation_ts[i.user_id] = i.timestamp

    # Second pass: filter out events before account creation
    cleaned: list[UserInteraction] = []
    dropped_users: set[str] = set()
    for i in interactions:
        if i.interaction_type == InteractionType.ACCOUNT_CREATION:
            cleaned.append(i)
        elif i.user_id in creation_ts and i.timestamp >= creation_ts[i.user_id]:
            cleaned.append(i)
        else:
            # Track users whose events are dropped (no ACCOUNT_CREATION or before it)
            if i.user_id not in creation_ts:
                dropped_users.add(i.user_id)

    if dropped_users:
        logging.warning(
            f"{len(dropped_users)} user(s) had interactions but no "
            f"ACCOUNT_CREATION event — all their events were dropped: "
            f"{sorted(dropped_users)[:10]}{'...' if len(dropped_users) > 10 else ''}"
        )

    return cleaned


def _enforce_close_account_invariant(
    interactions: list[UserInteraction],
) -> list[UserInteraction]:
    """
    Remove any interactions that occur after a CLOSE_ACCOUNT for the same user.
    Input must be sorted by timestamp.
    """
    closed_at: dict[str, datetime] = {}
    cleaned: list[UserInteraction] = []

    for i in interactions:
        if i.user_id in closed_at:
            # Skip any event after the user's account was closed
            continue
        cleaned.append(i)
        if i.interaction_type == InteractionType.CLOSE_ACCOUNT:
            closed_at[i.user_id] = i.timestamp

    return cleaned


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def generate_all(
    seed: int = 42,
    num_users: int = NUM_USERS,
    config: dict | None = None,
) -> tuple[list[User], list[UserProfile], list[UserInteraction]]:
    """
    Generate the complete mock dataset.

    Args:
        seed: Random seed for reproducibility.
        num_users: Number of regular (non-fake) users to generate.
        config: Dataset composition percentages (see generate.DATASET_CONFIG).

    Returns:
      (users, profiles, interactions) - all validated domain objects.
    """
    rng = random.Random(seed)
    now = datetime.now(timezone.utc) - timedelta(minutes=15)  # buffer so events stay in past during long run

    n_fake, n_pharmacy, n_porn, n_farming, n_harass, n_like = _fishy_counts(config)

    print(f"Generating {num_users} users...")
    users, used_emails, name_map = _generate_users(rng, now, num_users, config)
    print(f"  Created {len(users)} users ({sum(1 for u in users if not u.is_active)} inactive)")

    base = num_users
    print(f"Generating {n_fake} fake account users...")
    fake_users, fake_name_map = _generate_fake_account_users(rng, now, used_emails, base_idx=base, count=n_fake)
    users = users + fake_users
    name_map.update(fake_name_map)
    base += n_fake

    print(f"Generating {n_pharmacy} pharmacy phishing users...")
    pharmacy_users, pharmacy_name_map = _generate_pharmacy_users(rng, now, used_emails, base_idx=base, count=n_pharmacy, config=config)
    users = users + pharmacy_users
    name_map.update(pharmacy_name_map)
    base += n_pharmacy

    print(f"Generating {n_porn} covert porn users...")
    porn_users, porn_name_map = _generate_covert_porn_users(rng, now, used_emails, base_idx=base, count=n_porn, config=config)
    users = users + porn_users
    name_map.update(porn_name_map)
    base += n_porn

    print(f"Generating {n_farming} account farming users...")
    farming_users, farming_name_map = _generate_account_farming_users(rng, now, used_emails, base_idx=base, count=n_farming)
    users = users + farming_users
    name_map.update(farming_name_map)
    base += n_farming

    print(f"Generating {n_harass} harassment + {n_like} like inflation users...")
    harass_users, harass_name_map = _generate_harassment_users(rng, now, used_emails, base_idx=base, count=n_harass)
    users = users + harass_users
    name_map.update(harass_name_map)
    base += n_harass
    like_users, like_name_map = _generate_like_inflation_users(rng, now, used_emails, base_idx=base, count=n_like)
    users = users + like_users
    name_map.update(like_name_map)
    print(f"  Total users: {len(users)}")

    print("Generating profiles (Zipf connections)...")
    profiles = _generate_profiles(users, name_map, rng, now, config)
    conns = [p.connections_count for p in profiles]
    conns.sort()
    median_conn = conns[len(conns) // 2]
    max_conn = conns[-1]
    print(f"  Created {len(profiles)} profiles (connections: median={median_conn}, max={max_conn})")

    print(f"Generating interactions ({INTERACTION_WINDOW_DAYS}-day window)...")
    interactions = _generate_interactions(users, rng, now, config)
    print(f"  Created {len(interactions)} interactions")

    return users, profiles, interactions
