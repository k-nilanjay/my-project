"""
compute_eta_effective.py — Day 10 script
Computes eta_effective_h = eta_nominal_h / AF for each failure_log row.
Formula: AF = exp[(Ea/k) * (1/T_use - 1/T_stress)]
T_use   = nominal operating temperature per component (locked Day 5)
T_stress = alarm threshold temperature per component  (locked Day 6)
"""

import sys, sqlite3, math

sys.path.insert(0, 'python')

BOLTZMANN_EV_PER_K = 8.617e-5
KELVIN_OFFSET = 273.15

# Nominal operating temperatures — locked Day 5 (simulate.py SimulationConfig.nominal_temperatures)
T_NOMINAL = {
    1: 70.0,    # Bearing
    2: None,    # Shaft — Arrhenius not applicable
    3: 110.0,   # Motor Housing
    4: 60.0,    # Coupling
    5: 75.0,    # Gearbox
}

# Alarm threshold temperatures used as T_stress (conservative design, locked Day 6)
# Source: SENSOR_THRESHOLDS in etl.py and seed.sql
T_STRESS = {
    1: 80.0,    # Bearing: sensor 12 alarm = 80.0 degC
    2: None,    # Shaft: no thermal stress
    3: 130.0,   # Motor Housing: sensor 31 alarm = 130.0 degC
    4: 70.0,    # Coupling: no direct temp sensor; use T_nominal + 10C conservative estimate
    5: 90.0,    # Gearbox: sensor 53 alarm = 90.0 degC
}


def arrhenius_af(ea_ev, t_use_c, t_stress_c):
    """AF = exp[(Ea/k) * (1/T_use - 1/T_stress)]; temperatures in Celsius."""
    t_use_k = t_use_c + KELVIN_OFFSET
    t_stress_k = t_stress_c + KELVIN_OFFSET
    return math.exp((ea_ev / BOLTZMANN_EV_PER_K) * (1.0 / t_use_k - 1.0 / t_stress_k))


def main():
    conn = sqlite3.connect('data/manufacturing.db')

    rows = conn.execute(
        'SELECT failure_id, component_id, eta_nominal_h, ea_ev FROM failure_log ORDER BY failure_id'
    ).fetchall()

    print('failure_id | comp | eta_nominal_h | ea_ev | AF      | eta_effective_h')
    print('-' * 72)

    updates = []
    for r in rows:
        fid, cid, eta_nom, ea_ev = r
        t_nom = T_NOMINAL.get(cid)
        t_stress = T_STRESS.get(cid)

        if t_nom is not None and ea_ev is not None and t_stress is not None:
            af = arrhenius_af(ea_ev, t_nom, t_stress)
            eta_eff = eta_nom / af
            eta_eff_str = str(round(eta_eff, 2))
        else:
            af = 1.0
            eta_eff = None
            eta_eff_str = "NULL"

        af_str = str(round(af, 4))
        print(f'{fid:10d} | {cid:4d} | {eta_nom:13.1f} | {str(ea_ev):5s} | {af_str:7s} | {eta_eff_str}')

        if eta_eff is not None:
            updates.append((eta_eff, fid))

    print()
    print(f'Updating {len(updates)} rows with eta_effective_h ...')

    conn.executemany(
        'UPDATE failure_log SET eta_effective_h = ? WHERE failure_id = ?',
        updates
    )
    conn.commit()

    # Verify
    count = conn.execute('SELECT COUNT(*) FROM failure_log WHERE eta_effective_h IS NOT NULL').fetchone()[0]
    print(f'Rows with eta_effective_h populated: {count}')

    # Print final table
    final = conn.execute(
        '''SELECT fl.failure_id, c.component_name, fl.cycle_number,
                  fl.ttf_hours, fl.eta_nominal_h, fl.ea_ev, fl.eta_effective_h
           FROM failure_log fl
           JOIN components c ON c.component_id = fl.component_id
           ORDER BY fl.failure_id'''
    ).fetchall()
    print()
    print('failure_id | component     | cycle | ttf_h    | eta_nom | ea_ev | eta_eff')
    print('-' * 80)
    for row in final:
        fid, cname, cyc, ttf, eta_nom, ea, eta_eff = row
        ea_s = str(round(ea, 2)) if ea is not None else 'NULL'
        ee_s = str(round(eta_eff, 1)) if eta_eff is not None else 'NULL'
        print(f'{fid:10d} | {cname:13s} | {cyc:5d} | {ttf:8.2f} | {eta_nom:7.1f} | {ea_s:5s} | {ee_s}')

    conn.close()
    print('\nDONE — eta_effective_h updated for all applicable rows.')


if __name__ == '__main__':
    main()
