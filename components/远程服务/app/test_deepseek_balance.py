import unittest
from unittest.mock import Mock,patch
from pathlib import Path
from deepseek_balance import DeepSeekBalanceService, normalize_balance


class DeepSeekBalanceTests(unittest.TestCase):
    def sample(self):return {'is_available':True,'balance_infos':[{'currency':'CNY','total_balance':'12.3400','granted_balance':'2.34','topped_up_balance':'10.00'}],'api_key':'PRIVATE_SECRET'}

    def test_amounts_are_strings_and_credentials_never_public(self):
        value=normalize_balance(self.sample())
        self.assertEqual(value['balances'][0],{'currency':'CNY','total':'12.3400','granted':'2.34','topped_up':'10.00'})
        self.assertNotIn('PRIVATE',str(value))

    def test_zero_and_false_are_valid_not_missing(self):
        value=normalize_balance({'is_available':False,'balance_infos':[{'currency':'USD','total_balance':'0.00'}]})
        self.assertEqual(value['status'],'available');self.assertFalse(value['is_available'])
        self.assertEqual(value['balances'][0]['total'],'0.00');self.assertIsNone(value['balances'][0]['granted'])

    def test_invalid_values_never_become_zero(self):
        for amount in [None,0,True,'NaN','Infinity','<script>','1e100','1'*100]:
            data=self.sample();data['balance_infos'][0]['total_balance']=amount
            value=normalize_balance(data)
            self.assertEqual(value['status'],'unavailable');self.assertEqual(value['balances'],[])
        data=self.sample();data['balance_infos'][0]['currency']='PRIVATE'
        self.assertEqual(normalize_balance(data)['balances'],[])

    def test_cache_expiry_failure_and_close(self):
        clock=[0];probe=Mock(return_value=self.sample());service=DeepSeekBalanceService(probe=probe,clock=lambda:clock[0])
        self.assertEqual(service.read()['status'],'available');self.assertTrue(service.read()['cached']);probe.assert_called_once()
        clock[0]=31;probe.side_effect=RuntimeError('PRIVATE_KEY')
        value=service.read();self.assertEqual(value['status'],'unavailable');self.assertNotIn('PRIVATE',str(value));self.assertEqual(value['balances'],[])
        service.close();self.assertEqual(service.read()['status'],'unavailable')

    def test_each_currency_kept_separate_and_duplicate_rejected(self):
        data=self.sample();data['balance_infos'].append({'currency':'USD','total_balance':'5.50'})
        self.assertEqual(len(normalize_balance(data)['balances']),2)
        data['balance_infos'].append(data['balance_infos'][0])
        self.assertEqual(normalize_balance(data)['status'],'unavailable')

    def test_unexpected_io_error_reaps_owned_worker(self):
        process=Mock();process.communicate.side_effect=OSError('PRIVATE_IO');process.poll.return_value=None
        service=DeepSeekBalanceService()
        with patch('deepseek_balance.harness_paths',return_value=(Path('fake-executable'),Path('unused'))),patch.object(service,'_spawn',return_value=process):
            self.assertEqual(service.read()['status'],'unavailable')
        process.wait.assert_called();process.stdin.close.assert_called()
        service.close()


if __name__=='__main__':unittest.main()
