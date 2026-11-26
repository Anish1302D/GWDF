"""Risk classification, empirical threshold calibration, and multilingual farmer advice."""

from __future__ import annotations

from typing import Any
import numpy as np
import pandas as pd

ADVICE_CATALOG: dict[str, dict[str, str]] = {
    "Safe": {
        "en": "Groundwater levels look stable for the coming season. Continue balanced irrigation and maintain farm ponds or recharge pits to preserve reserves.",
        "hi": "आगामी मौसम के लिए भूजल स्तर स्थिर दिख रहा है। संतुलित सिंचाई जारी रखें और जल भंडार बनाए रखने के लिए खेत तालाब या रिचार्ज गड्ढों की देखभाल करें।",
        "mr": "आगामी हंगामासाठी भूजल पातळी स्थिर दिसत आहे. संतुलित सिंचन सुरू ठेवा आणि पाणी साठा टिकवण्यासाठी शेततळे किंवा पुनर्भरण खड्ड्यांची निगा राखा.",
    },
    "Watch": {
        "en": "Water levels show moderate stress. Prefer low-water crops (millets, pulses), use drip or sprinkler irrigation, and avoid drilling deeper borewells without checking local recharge.",
        "hi": "भूजल स्तर पर मध्यम दबाव के संकेत हैं। कम पानी वाली फसलें (बाजरा, दालें) चुनें, ड्रिप या स्प्रिंकलर सिंचाई अपनाएं और बिना स्थानीय जांच के गहरा बोरवेल न खुदवाएं।",
        "mr": "भूजल पातळीवर मध्यम ताण जाणवत आहे. कमी पाण्याची पिके (बाजरी, कडधान्ये) निवडा, ठिबक किंवा तुषार सिंचन वापरा आणि तज्ज्ञांच्या सल्ल्याशिवाय खोल बोअरवेल खोदू नका.",
    },
    "Critical": {
        "en": "High depletion risk predicted next season. Avoid water-intensive crops (like sugarcane or summer paddy), prioritize drinking water conservation, and consult local water planners for recharge or tanker support.",
        "hi": "अगले मौसम में भूजल की भारी कमी का जोखिम है। अधिक पानी वाली फसलों (जैसे गन्ना या ग्रीष्मकालीन धान) से बचें, पेयजल संरक्षण को प्राथमिकता दें और जल विभाग से सहायता के लिए संपर्क करें।",
        "mr": "पुढील हंगामात भूजल पातळीत तीव्र घटीचा धोका आहे. जास्त पाण्याची पिके (जसे ऊस किंवा उन्हाळी भात) टाळा, पिण्याच्या पाण्याचे संवर्धन करा आणि स्थानिक जल नियोजकांशी संपर्क साधा.",
    },
    "Insufficient Data": {
        "en": "Monitoring well data for this block is too limited to produce a reliable forecast. Check nearby blocks or official CGWB/GSDA advisories before major irrigation decisions.",
        "hi": "इस ब्लॉक के लिए विश्वसनीय पूर्वानुमान बनाने हेतु पर्याप्त निगरानी कुओं का डेटा उपलब्ध नहीं है। सिंचाई के बड़े निर्णयों से पहले नजदीकी ब्लॉक या आधिकारिक सलाह देखें।",
        "mr": "या तालुक्यासाठी विश्वसनीय अंदाज तयार करण्यासाठी पुरेसा निरीक्षण विहिरींचा डेटा उपलब्ध नाही. सिंचनाचे मोठे निर्णय घेण्यापूर्वी जवळच्या तालुक्याची माहिती किंवा शासकीय सल्ला घ्या.",
    },
}

DEFAULT_THRESHOLDS: dict[str, float] = {
    "critical_depth_mbgl": 12.5,
    "watch_depth_mbgl": 8.0,
    "critical_combo_depth_mbgl": 9.5,
    "critical_combo_yoy_mbgl": 1.2,
    "critical_yoy_mbgl": 2.0,
    "watch_yoy_mbgl": 0.65,
    "critical_trend_mbgl_yr": 0.8,
    "watch_trend_mbgl_yr": 0.35,
    "score_depth_scale": 18.0,
    "score_yoy_scale": 2.5,
    "score_trend_scale": 1.2,
}


def calibrate_thresholds_from_data(depths: pd.Series) -> dict[str, float]:
    """Calibrate depth thresholds to target state's empirical aquifer depth distribution."""
    clean = depths.dropna()
    if len(clean) < 30:
        return dict(DEFAULT_THRESHOLDS)

    p65 = float(np.percentile(clean, 65))
    p85 = float(np.percentile(clean, 85))
    p95 = float(np.percentile(clean, 95))

    thresholds = dict(DEFAULT_THRESHOLDS)
    thresholds["watch_depth_mbgl"] = round(max(6.5, min(11.0, p65)), 2)
    thresholds["critical_depth_mbgl"] = round(max(10.5, min(18.0, p85)), 2)
    thresholds["critical_combo_depth_mbgl"] = round(
        0.5 * (thresholds["watch_depth_mbgl"] + thresholds["critical_depth_mbgl"]), 2
    )
    thresholds["score_depth_scale"] = round(max(14.0, p95), 2)
    return thresholds


def classify_risk(
    predicted_depth_mbgl: float,
    yoy_delta_mbgl: float,
    trend_5yr_mbgl: float,
    thresholds: dict[str, float] | None = None,
) -> tuple[str, float]:
    """Return `(risk_class, risk_score)` where higher `mbgl` / positive `yoy_delta` = worse stress."""
    t = thresholds or DEFAULT_THRESHOLDS
    d = float(predicted_depth_mbgl)
    yoy = float(yoy_delta_mbgl)
    tr = float(trend_5yr_mbgl)

    depth_comp = min(max(d / t["score_depth_scale"], 0.0), 1.35) * 44.0
    yoy_comp = min(max((yoy + 0.5) / (t["score_yoy_scale"] + 0.5), 0.0), 1.0) * 34.0
    trend_comp = min(max((tr + 0.3) / (t["score_trend_scale"] + 0.3), 0.0), 1.0) * 22.0
    raw_score = min(99.5, round(depth_comp + yoy_comp + trend_comp, 1))

    is_critical = (
        d >= t["critical_depth_mbgl"]
        or (d >= t["critical_combo_depth_mbgl"] and yoy >= t["critical_combo_yoy_mbgl"])
        or yoy >= t["critical_yoy_mbgl"]
        or (tr >= t["critical_trend_mbgl_yr"] and d >= t["watch_depth_mbgl"])
    )
    if is_critical:
        boosted = round(68.0 + 0.315 * raw_score, 1)
        return "Critical", min(99.5, max(raw_score, boosted))

    is_watch = (
        d >= t["watch_depth_mbgl"]
        or yoy >= t["watch_yoy_mbgl"]
        or tr >= t["watch_trend_mbgl_yr"]
    )
    if is_watch:
        scaled = round(36.0 + 0.45 * raw_score, 1)
        return "Watch", min(67.9, max(36.0, scaled))

    return "Safe", min(35.9, raw_score)


def get_advice(risk_class: str) -> dict[str, str]:
    """Return localized `{en, hi, mr}` advice dictionary for `risk_class`."""
    return dict(ADVICE_CATALOG.get(risk_class, ADVICE_CATALOG["Insufficient Data"]))
