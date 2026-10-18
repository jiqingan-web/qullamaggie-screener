# 流动性较好的美股代码池（标普500核心 + 常见高波动成长股）
# 用于免费数据源扫描，避免全市场过重请求

UNIVERSE = [
    "AAPL", "MSFT", "NVDA", "AMD", "AVGO", "META", "GOOGL", "GOOG", "AMZN", "TSLA",
    "NFLX", "CRM", "ORCL", "ADBE", "INTC", "QCOM", "TXN", "AMAT", "LRCX", "KLAC",
    "MU", "SNPS", "CDNS", "NOW", "SNOW", "PLTR", "CRWD", "PANW", "DDOG", "NET",
    "ZS", "FTNT", "TEAM", "WDAY", "INTU", "SHOP", "UBER", "LYFT", "ABNB", "COIN",
    "HOOD", "MSTR", "APP", "SMCI", "ARM", "MRVL", "ON", "NXPI", "ADI", "DELL",
    "HPQ", "IBM", "CSCO", "ANET", "COST", "WMT", "TGT", "HD", "LOW", "NKE",
    "SBUX", "MCD", "CMG", "DPZ", "LULU", "TJX", "ROST", "BABA", "JD", "PDD",
    "MELI", "SE", "ETSY", "RBLX", "DKNG", "PENN", "WYNN", "LVS", "MGM", "JPM",
    "BAC", "WFC", "GS", "MS", "C", "BLK", "SCHW", "AXP", "V", "MA",
    "PYPL", "SOFI", "AFRM", "UPST", "MQ", "UNH", "JNJ", "LLY", "ABBV", "MRK",
    "PFE", "TMO", "ABT", "DHR", "ISRG", "VRTX", "REGN", "GILD", "AMGN", "BIIB",
    "MRNA", "BNTX", "DXCM", "ILMN", "CAT", "DE", "GE", "HON", "UPS", "FDX",
    "BA", "LMT", "RTX", "NOC", "XOM", "CVX", "COP", "SLB", "OXY", "MPC",
    "VLO", "DVN", "FANG", "FCX", "NEM", "AA", "CLF", "NUE", "DIS", "CMCSA",
    "T", "VZ", "TMUS", "SPOT", "ROKU", "TTWO", "EA", "CELH", "CAVA", "DUOL",
    "PATH", "AI", "IONQ", "RGTI", "QBTS", "RKLB", "ASTS", "LUNR", "JOBY", "ACHR",
    "SOUN", "BBAI", "UPXI", "HIMS", "OSCR", "LMND", "ROOT", "OPEN", "Z", "ZG",
    "TTD", "MGNI", "PUBM", "RAMP", "GTLB", "S", "ESTC", "MDB", "BILL", "TOST",
    "FOUR", "DOCN", "FROG", "PCOR", "ENPH", "SEDG", "FSLR", "RUN", "PLUG", "BE",
    "CHPT", "LCID", "RIVN", "NIO", "XPEV", "LI", "F", "GM", "CVNA", "AN",
    "KMX", "CAR", "ABG", "GME", "AMC", "BB", "NOK", "SPY", "QQQ", "IWM",
    "BRK-B", "PG", "KO", "PEP", "PM", "MO", "MDLZ", "CL", "EL", "KVUE",
    "CVS", "CI", "HUM", "CNC", "ELV", "ACN", "ADP", "PAYX", "FIS", "FISV",
    "GPN", "MMC", "AON", "AJG", "PGR", "TRV", "ALL", "MET", "PRU", "AIG",
    "SPGI", "MCO", "ICE", "CME", "NDAQ", "EQIX", "DLR", "AMT", "CCI", "PLD",
    "PSA", "O", "SPG", "WELL", "NEE", "DUK", "SO", "D", "AEP", "SRE",
    "EXC", "XEL", "LIN", "APD", "SHW", "ECL", "DD", "DOW", "PPG", "SYK",
    "BSX", "MDT", "ZBH", "EW", "BDX", "BAX", "MAR", "HLT", "BKNG", "EXPE",
    "CCL", "RCL", "NCLH", "DAL", "UAL", "AAL", "LUV", "ALK", "CHTR", "PARA",
    "WBD", "FOX", "FOXA", "NWSA", "SNAP", "PINS", "MTCH", "BMBL", "ZM", "DOCU",
    "OKTA", "TWLO", "U", "SONY", "ASML", "TSM", "UMC", "SAP", "GRAB", "CPNG",
    "GOLD", "AU", "KGC", "AG", "HL", "BTU", "HCC", "STLD", "RS", "CMC",
    "PH", "EMR", "ETN", "ROK", "IR", "XYL", "TT", "CARR", "OTIS", "JCI",
    "CMI", "PCAR", "URI", "FAST", "GWW", "CTAS", "CPRT", "ODFL", "XPO", "JBHT",
    "VRT", "VST", "CEG", "TLN", "NRG", "AXON", "BWXT", "KTOS", "HII", "GD",
    "FIX", "PWR", "EME", "ACM", "J", "BLDR", "DHI", "LEN", "PHM", "TOL",
    "NVR", "KBH", "MAS", "OC", "AOS", "WMS", "XYZ", "NU",
]

# 排除指数基金（仅用于市场状态）
INDEX_TICKERS = {"SPY", "QQQ", "IWM"}

def get_scan_universe():
    seen = set()
    out = []
    for t in UNIVERSE:
        if t in INDEX_TICKERS:
            continue
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out
