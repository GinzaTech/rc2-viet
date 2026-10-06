import unittest
from review import translate_sentence, harmonize, technical, valid,compose_reviewed,reviewed_clauses
from user_wording import apply_user_wording

class ReviewTests(unittest.TestCase):
    def test_negation_and_reason(self):
        self.assertEqual(translate_sentence('Aircraft landing. Unable to enter MasterShots'),
                         'Máy bay đang hạ cánh. Không thể dùng MasterShots')
    def test_known_action_feature(self):
        self.assertEqual(translate_sentence('Unable to shoot 48MP photos when using FocusTrack'),
                         'Không thể chụp ảnh 48MP khi dùng FocusTrack')
    def test_unknown_action_stays_unhandled(self):
        self.assertIsNone(translate_sentence('Unable to sing when using Something'))
    def test_protected_numbers_and_format(self):
        self.assertFalse(valid('Metric (km)','Hệ mét (mm)'))
        self.assertFalse(valid('Value %1$s at 5°C','Giá trị %s ở 5°C'))
        self.assertTrue(valid('Value %1$s at 5°C','Giá trị %1$s ở 5°C'))
    def test_audio_recording_is_not_video(self):
        self.assertEqual(harmonize('Audio recording','Ghi âm'),'Ghi âm')
        self.assertEqual(harmonize('Flight records','Ghi âm máy bay'),'Nhật ký bay')
    def test_technical_data(self):
        self.assertTrue(technical('cubic-bezier(0.3, 0.0, 0.8, 0.2)'))
        self.assertTrue(technical('20,AD\n784,AE'))
        self.assertFalse(technical('Record video at 30 fps'))
    def test_complete_clause_reuse_and_unknown_reason(self):
        clauses=reviewed_clauses({'Battery error':'Lỗi pin','Unable to take off':'Không thể cất cánh'})
        self.assertEqual(compose_reviewed('Battery error. Unable to take off',clauses),'Lỗi pin. Không thể cất cánh')
        self.assertIsNone(compose_reviewed('Battery error. Unknown emergency',clauses))
    def test_user_terms_keep_formats_and_numbers(self):
        source='Return to Home (RTH): %1$s at 120 m'
        result=apply_user_wording('quay về điểm đã đặt (RTH): %1$s ở 120 m')
        self.assertEqual(result,'quay về vị trí ban đầu (RTH): %1$s ở 120 m')
        self.assertTrue(valid(source,result))
    def test_unit_label_exception_is_limited_to_requested_label(self):
        self.assertTrue(valid('Metric (km)',apply_user_wording('Hệ mét (km)')))
        self.assertFalse(valid('Distance 5 km','Khoảng cách 5 Km'))

if __name__=='__main__': unittest.main()
