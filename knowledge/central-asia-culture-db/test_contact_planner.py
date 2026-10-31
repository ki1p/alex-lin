import copy
import unittest
from datetime import datetime
import contact_planner as cp


def at(value):return datetime.fromisoformat(value)


class ContactPlannerTests(unittest.TestCase):
    def test_23_local_warns_and_skips_weekend(self):
        r=cp.plan('KZ',at('2026-10-31T23:00:00+05:00'))
        self.assertEqual(r['status'],'quiet_hours')
        self.assertEqual(r['beijing_now'],'2026-11-01T02:00+08:00')
        self.assertEqual(r['next_candidate_local'],'2026-11-02T09:30+05:00')
        self.assertEqual(r['next_candidate_beijing'],'2026-11-02T12:30+08:00')
        self.assertIn('不要打扰',r['reminder_zh'])

    def test_all_five_countries_protect_23_for_all_channels(self):
        for country,offset in [('KZ',5),('UZ',5),('KG',6),('TJ',5),('TM',5)]:
            for channel in ['email','whatsapp','call']:
                r=cp.plan(country,at(f'2026-11-02T23:00:00+0{offset}:00'),channel)
                self.assertEqual(r['status'],'quiet_hours')
                self.assertFalse(r['automatically_sent'])
                self.assertFalse(r['automatically_scheduled'])

    def test_kyrgyzstan_time_difference(self):
        r=cp.plan('KG',at('2026-11-02T23:00:00+06:00'))
        self.assertEqual(r['beijing_now'],'2026-11-03T01:00+08:00')
        self.assertEqual(r['next_candidate_beijing'],'2026-11-03T11:30+08:00')

    def test_work_window_end_exclusive(self):
        r=cp.plan('KZ',at('2026-11-02T17:30:00+05:00'))
        self.assertEqual(r['status'],'outside_contact_window')
        self.assertEqual(r['next_candidate_local'],'2026-11-03T09:30+05:00')

    def test_tajik_lunch_deferred(self):
        r=cp.plan('TJ',at('2026-11-02T12:15:00+05:00'))
        self.assertEqual(r['status'],'outside_contact_window')
        self.assertEqual(r['next_candidate_local'],'2026-11-02T13:30+05:00')

    def test_tajik_holiday_and_weekend(self):
        r=cp.plan('TJ',at('2026-11-05T23:00:00+05:00'))
        self.assertEqual(r['next_candidate_local'],'2026-11-09T09:00+05:00')

    def test_kazakh_fixed_holiday(self):
        r=cp.plan('KZ',at('2026-12-16T10:00:00+05:00'))
        self.assertEqual(r['status'],'holiday')
        self.assertEqual(r['next_candidate_local'],'2026-12-17T09:30+05:00')

    def test_uzbek_conservative_start(self):
        r=cp.plan('UZ',at('2026-11-02T09:30:00+05:00'))
        self.assertEqual(r['next_candidate_local'],'2026-11-02T10:00+05:00')

    def test_customer_six_day_schedule(self):
        p={'schedule_confirmed':True,'working_days':[0,1,2,3,4,5]}
        r=cp.plan('TM',at('2026-10-31T10:00:00+05:00'),profile=p)
        self.assertEqual(r['status'],'within_contact_window')

    def test_customer_unavailable_day_wins(self):
        p={'unavailable_dates':['2026-11-02'],'confirmed_working_dates':['2026-11-02']}
        r=cp.plan('KZ',at('2026-11-02T10:00:00+05:00'),profile=p)
        self.assertEqual(r['status'],'customer_unavailable')
        self.assertEqual(r['next_candidate_local'],'2026-11-03T09:30+05:00')

    def test_confirmed_exceptional_work_day(self):
        p={'schedule_confirmed':True,'confirmed_working_dates':['2026-12-16']}
        r=cp.plan('KZ',at('2026-12-16T10:00:00+05:00'),profile=p)
        self.assertEqual(r['status'],'within_contact_window')

    def test_trip_timezone_does_not_apply_home_holiday(self):
        r=cp.plan('KZ',at('2026-12-16T06:00:00+00:00'),timezone_override='Asia/Dubai')
        self.assertEqual(r['local_now'],'2026-12-16T10:00+04:00')
        self.assertEqual(r['status'],'within_contact_window')
        self.assertTrue(any('出差地' in w for w in r['warnings']))

    def test_unknown_calendar_year_is_explicit(self):
        r=cp.plan('KZ',at('2027-01-04T10:00:00+05:00'))
        self.assertTrue(any('2027' in w for w in r['warnings']))
        self.assertFalse(r['calendar_complete'])

    def test_year_boundary_candidate_warns(self):
        r=cp.plan('UZ',at('2026-12-31T23:00:00+05:00'))
        self.assertTrue(r['next_candidate_local'].startswith('2027-'))
        self.assertTrue(any('2027' in w for w in r['warnings']))

    def test_early_morning_is_quiet(self):
        r=cp.plan('KZ',at('2026-11-02T06:00:00+05:00'))
        self.assertEqual(r['status'],'quiet_hours')
        self.assertEqual(r['next_candidate_local'],'2026-11-02T09:30+05:00')

    def test_unknown_country_rejected(self):
        with self.assertRaises(ValueError):cp.plan('CA')

    def test_naive_timestamp_rejected(self):
        with self.assertRaises(ValueError):cp.plan('KZ',at('2026-11-02T23:00:00'))

    def test_conflicting_country_rejected(self):
        with self.assertRaises(ValueError):cp.plan('KZ',profile={'country':'KG'})

    def test_invalid_clock_and_overlaps_rejected(self):
        for windows in [[['24:00','25:00']],[['12:00','11:00']],[['09:00','12:00'],['11:00','13:00']]]:
            with self.assertRaises(ValueError):cp.plan('KZ',profile={'contact_windows':windows})

    def test_invalid_weekdays_rejected(self):
        for days in [[],[7],[True],[0,0]]:
            with self.assertRaises(ValueError):cp.plan('KZ',profile={'working_days':days})

    def test_only_quiet_windows_do_not_produce_night_candidate(self):
        r=cp.plan('KZ',at('2026-11-02T23:00:00+05:00'),profile={'contact_windows':[['22:30','23:30']]})
        self.assertNotIn('next_candidate_local',r)

    def test_partial_overlap_is_trimmed(self):
        r=cp.plan('KZ',at('2026-11-02T06:00:00+05:00'),profile={'contact_windows':[['08:00','10:00']]})
        self.assertEqual(r['next_candidate_local'],'2026-11-02T08:30+05:00')

    def test_unknown_timezone_rejected(self):
        with self.assertRaises(ValueError):cp.plan('KZ',timezone_override='Mars/Unknown')

    def test_defaults_not_mutated_by_customer(self):
        data=cp.load_policy();before=copy.deepcopy(data)
        cp.plan('KZ',at('2026-11-02T10:00:00+05:00'),profile={'working_days':[0]},policy_data=data)
        self.assertEqual(data,before)

    def test_dst_gap_never_returns_nonexistent_wall_time(self):
        r=cp.plan('KZ',at('2026-03-29T00:00:00+00:00'),timezone_override='Europe/Berlin',profile={'working_days':[6],'contact_windows':[['02:30','04:00']],'quiet_hours':['22:00','01:00']})
        self.assertEqual(r['next_candidate_local'],'2026-03-29T03:30+02:00')

    def test_secondary_calendar_never_claims_complete(self):
        for country in ['UZ','KG','TJ','TM']:
            r=cp.plan(country,at('2026-11-02T06:00:00+00:00'))
            self.assertFalse(r['calendar_complete'])
            self.assertTrue(any('快照' in w for w in r['warnings']))


if __name__=='__main__':unittest.main()
