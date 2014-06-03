# -*- coding:utf-8 -*-
import math
from datetime import datetime

import os
parentdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.sys.path.insert(0,parentdir) 
from time_array import TimeArray
from pension_data import PensionData

from numpy import array, multiply
from pandas import Series

from regime import compare_destinie
from regime_prive import RegimePrive
from utils_pension import build_long_values, build_salref_bareme, print_multi_info_numpy
from trimesters_functions import trim_ass_by_year, validation_trimestre, sali_in_regime, trim_mda, imput_sali_avpf

code_avpf = 8
first_year_indep = 1949
first_year_avpf = 1972
    
class RegimeGeneral(RegimePrive):
    
    def __init__(self):
        RegimePrive.__init__(self)
        self.regime = 'RG'
        self.code_regime = [3,4]
        self.param_name_bis = 'prive.RG'
     
    def get_trimesters_wages(self, data):
        trimesters = dict()
        wages = dict()
        trim_maj = dict()
        to_other = dict()
        
        info_ind = data.info_ind
        
        salref = build_salref_bareme(self.P_longit.common, data.first_date.year, data.last_date.year + 1)
        trimesters['cot'], wages['cot'] = validation_trimestre(data, self.code_regime, salref)
        trimesters['ass'], _ = trim_ass_by_year(data, self.code_regime, compare_destinie)
        
        data_avpf = data.selected_dates(first_year_avpf)
        data_avpf.sali = imput_sali_avpf(data_avpf, code_avpf, self.P_longit, compare_destinie)
        salref = build_salref_bareme(self.P_longit.common, data_avpf.first_date.year, data_avpf.last_date.year + 1)
        # Allocation vieillesse des parents au foyer : nombre de trimestres attribués 
        trimesters['avpf'], wages['avpf'] = validation_trimestre(data_avpf, code_avpf, salref + 1)
        P_mda = self.P.prive.RG.mda
        trim_maj['DA'] = trim_mda(info_ind, P_mda)*(trimesters['cot'].sum(1)>0)
        output = {'trimesters': trimesters, 'wages': wages, 'maj': trim_maj}
        return output, to_other

class RegimeSocialIndependants(RegimePrive):
    
    def __init__(self):
        RegimePrive.__init__(self)
        self.regime = 'RSI'
        self.code_regime = [7]
        self.param_name_bis = 'indep.rsi'

    def get_trimesters_wages(self, data):
        trimesters = dict()
        wages = dict()
        trim_maj = dict()
        to_other = dict()
        
        workstate = data.workstate
        sali = data.sali
        
        reduce_data = data.selected_dates(first=first_year_indep)
        salref = build_salref_bareme(self.P_longit.common, reduce_data.first_date.year, data.last_date.year + 1)
        trimesters['cot'], _ = validation_trimestre(reduce_data, self.code_regime, salref)

        # TODO : pour l'instant tous les trimestres assimilés sont imputés au RG
        #nb_trim_ass, _ = trim_ass_by_year(reduce_data, self.code_regime, compare_destinie)
        #trimesters['ass'] = nb_trim_ass 
        wages['regime'] = sali_in_regime(workstate, sali, self.code_regime)
        P_mda = self.P.prive.RG.mda
        trim_maj['DA'] = trim_mda(data.info_ind, P_mda)*(trimesters['cot'].sum(1)>0)
        output = {'trimesters': trimesters, 'wages': wages, 'maj': trim_maj}
        return output, to_other