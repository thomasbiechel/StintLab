

def test_standing_start_after_sc_start_is_not_a_red_flag():
    # Kuala Lumpur 2026: Start hinter dem Safety Car, stehender Start in Runde 2, keine rote Flagge
    from stintlab.race_control import neutral_laps
    rc = [{"lap": 1, "category": "Other", "message": "SAFETY CAR LIGHTS ON"},
          {"lap": 2, "category": "Other", "message": "STANDING START"},
          {"lap": 9, "category": "SafetyCar", "message": "SAFETY CAR DEPLOYED"},
          {"lap": 12, "category": "SafetyCar", "message": "SAFETY CAR IN THIS LAP"}]
    kinds = neutral_laps(rc)
    assert kinds.get(2) == "SC" and kinds.get(3) == "SC"
    assert "RED" not in kinds.values()


def test_vsc_turning_into_safety_car():
    from stintlab.race_control import neutral_laps
    rc = [{"lap": 43, "category": "SafetyCar", "message": "VSC DEPLOYED"},
          {"lap": 45, "category": "SafetyCar", "message": "SAFETY CAR DEPLOYED"},
          {"lap": 51, "category": "SafetyCar", "message": "SAFETY CAR IN THIS LAP"}]
    kinds = neutral_laps(rc)
    assert kinds[43] == kinds[44] == "VSC"
    assert all(kinds[n] == "SC" for n in range(45, 52))
