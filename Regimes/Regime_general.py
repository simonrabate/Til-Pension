# -*- coding:utf-8 -*-
import math
import numpy as np
import pandas as pd
from datetime import datetime

import os
parentdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.sys.path.insert(0,parentdir) 
from time_array import TimeArray

from regime import RegimeBase
from utils_pension import valbytranches, table_selected_dates, build_long_values, build_salref_bareme
from pension_functions import calculate_SAM, nb_trim_surcote, unemployment_trimesters

code_avpf = 8
code_chomage = 5
first_year_sal = 1949
compare_destinie = True 
sal_avpf = False

def date_(year, month, day):
    return datetime.date(year, month, day)

class RegimeGeneral(RegimeBase):
    
    def __init__(self):
        RegimeBase.__init__(self)
        self.regime = 'RG'
        self.code_regime = [3,4]
        self.param_name = 'prive.RG'
     
     
    def get_trimester(self, workstate, sali):
        output = {}
        nb_trim_cot = self.nb_trim_cot(workstate, sali)
        output['trim_cot_RG']  = nb_trim_cot.sum(axis=1)
        output['trim_ass'] = self.nb_trim_ass(workstate, nb_trim_cot)
        output['trim_maj'] = self.nb_trim_maj(workstate, sali)
        return output        
            
    def nb_trim_cot(self, workstate, sali, code=None):
        ''' Nombre de trimestres côtisés pour le régime général 
        ref : code de la sécurité sociale, article R351-9
         '''
        # Selection des salaires à prendre en compte dans le décompte (mois où il y a eu côtisation au régime)
        if code is None:
            code = self.code_regime
        time_step = self.time_step
            
        wk_selection = workstate.isin(code)
        sal_selection = TimeArray(wk_selection*sali.array, sali.dates)
        if time_step == 'month':
            sal_selection.translate_frequency(output_frequency='year',
                                                  method='sum', inplace=True)
        sal_selection.array[np.isnan(sal_selection.array)] = 0
        self.sal_RG = sal_selection    #TODO: remove
        
        salref = build_salref_bareme(self.P_longit.common, first_year_sal, self.yearsim)
        nb_trim_cot = np.minimum(np.divide(sal_selection.array, salref).astype(int),4)
        return nb_trim_cot
        
    def nb_trim_ass(self, workstate, nb_trim_cot):
        ''' 
        Comptabilisation des périodes assimilées à des durées d'assurance
        Pour l"instant juste chômage workstate == 5 (considéré comme indemnisé) 
        qui succède directement à une période de côtisation au RG workstate == [3,4]
        TODO: ne pas comptabiliser le chômage de début de carrière
        '''
        nb_trim_chom, table_chom = unemployment_trimesters(workstate.array, code_regime=self.code_regime,
                                                            input_step=self.time_step, output='table_unemployement')
        nb_trim_ass = nb_trim_chom # TODO: + nb_trim_war + ....
        trim_by_year = TimeArray(array=nb_trim_cot + table_chom, 
                                       dates=[100*year + 1 for year in range(first_year_sal, self.yearsim)])
        return nb_trim_ass
            
    def nb_trim_maj(self, workstate, sali):
        ''' Trimestres majorants acquis au titre de la MDA, 
            de l'assurance pour congé parental ou de l'AVPF '''
        
        def _mda(info_child, list_id, yearsim):
            #TODO: remove the pandas call
            ''' Majoration pour enfant à charge : nombre de trimestres acquis
            Rq : cette majoration n'est applicable que pour les femmes dans le RG'''
            mda = pd.DataFrame({'mda': np.zeros(len(list_id))}, index=list_id)
            # TODO: distinguer selon l'âge des enfants après 2003
            # ligne suivante seulement if info_child['age_enf'].min() > 16 :
            if yearsim < 1972 :
                return mda
            elif yearsim <1975:
                # loi Boulin du 31 décembre 1971 
                mda.iloc[info_child.index.values, 'mda'] = 4*info_child.values
                mda.loc[mda['mda'] < 2, 'mda'] = 0
                return mda.astype(int)
            elif yearsim <2004:
                mda.loc[info_child.index.values, 'mda'] = 4*info_child.values
                mda.loc[mda['mda'] < 2, 'mda'] = 0
                return mda.astype(int)
            else:
                # Réforme de 2003 : min(1 trimestre à la naissance + 1 à chaque anniv, 8)
                mda.loc[info_child.index.values, 'mda'] = 4*info_child.values
                mda.loc[mda['mda'] < 2, 'mda'] = 0
                return mda['mda'].astype(int)
            
        def _avpf(workstate, sali):
            ''' Allocation vieillesse des parents au foyer : nombre de trimestres acquis'''
            avpf_selection = workstate.isin([code_avpf])
            avpf_selection.translate_frequency(output_frequency='year', inplace=True)
            #avpf_selection = avpf_selection[[col_year for col_year in avpf_selection.columns if str(col_year)[-2:]=='01']]

            salref = build_salref_bareme(self.P_longit.common, first_year_sal, self.yearsim) #TODO: it's used twice so once too much
            sal_avpf = avpf_selection*np.divide(sali, salref) # Si certains salaires son déjà attribués à des états d'avpf on les conserve (cf.Destinie)
            nb_trim = avpf_selection.sum(axis=1)*4
            
            sal_avpf_array = sal_avpf_array*(avpf_selection != 0)
            sal_avpf = TimeArray(sal_avpf_array, avpf_selection.dates) # Si certains salaires son déjà attribués à des états d'avpf on les conserve (cf.Destinie)

            return nb_trim, avpf_selection, sal_avpf
        
        child_mother = self.info_ind.loc[self.info_ind['sexe'] == 1, 'nb_born']
        list_id = self.info_ind.index
        yearsim = self.yearsim
        if child_mother is not None:
            nb_trim_mda = _mda(child_mother, list_id, yearsim)
        else :
            nb_trim_mda = 0
            
        nb_trim_avpf, trim_avpf, sal_avpf = _avpf(workstate.copy(), sali)

        # Les trimestres d'avpf sont comptabilisés dans le calcul du SAM
        self.trim_avpf = trim_avpf
        self.sal_avpf = sal_avpf
        return nb_trim_mda + nb_trim_avpf
    
    def SAM(self):
        ''' Calcul du salaire annuel moyen de référence : 
        notamment application du plafonnement à un PSS'''
        yearsim = self.yearsim
        P = reduce(getattr, self.param_name.split('.'), self.P)
        nb_years = valbytranches(P.nb_sam, self.info_ind)
        plafond = build_long_values(param_long=self.P_longit.common.plaf_ss, first_year=first_year_sal, last_year=yearsim)
        revalo = build_long_values(param_long=self.P_longit.prive.RG.revalo, first_year=first_year_sal, last_year=yearsim)
        smic_long = build_long_values(param_long=self.P_longit.common.smic_proj, first_year=1972, last_year=yearsim) # avant pas d'avpf
        
        for i in range(1, len(revalo)) :
            revalo[:i] *= revalo[i]
            
        def _sal_for_sam(sal_RG, trim_avpf, smic, data_type='numpy'):
            ''' construit la matrice des salaires de références '''
            if data_type == 'numpy':
                # TODO: check if annual step in sal_avpf and sal_RG
                first_ix_avpf = 1972 - first_year_sal
                trim_avpf.array = trim_avpf.array[:,first_ix_avpf:]
                sal_avpf = np.multiply((trim_avpf.array != 0), smic) #*2028 = 151.66*12 if horaires
                sal_RG.array[:,first_ix_avpf:] += sal_avpf
                return np.round(sal_RG.array,2)
            if data_type == 'pandas':
                trim_avpf = table_selected_dates(trim_avpf, self.dates, first_year=1972, last_year=yearsim)
                sal_avpf = np.multiply((trim_avpf != 0), smic ) #*2028 = 151.66*12 if horaires
                dates_avpf = [date for date in sal_RG.columns if date >= 197201]
                sal_RG.loc[:,dates_avpf] += sal_avpf.loc[:,dates_avpf]
                return np.round(sal_RG,2)
                    
        
        sal_sam = _sal_for_sam(self.sal_RG, self.trim_avpf, smic_long)
        
        SAM = calculate_SAM(sal_sam, nb_years, time_step='year', plafond=plafond, revalorisation=revalo)
        self.sal_RG = sal_sam
        #print "plafond : {},revalo : {}, sal_sam: {}, calculate_sam:{}".format(t1-t0,t2-t1,t3 -t2, t4 - t3)
        return np.round(SAM, 2)
    
    def assurance_maj(self, trim_RG, trim_tot, agem):
        ''' Détermination de la durée d'assurance corrigée introduite par la réforme Boulin
        (majoration quand départ à la retraite après 65 ans) '''
        P = reduce(getattr, self.param_name.split('.'), self.P)
        year = self.yearsim

        if year < 1983:
            return trim_RG
        elif year < 2004 :
            trim_majo = np.maximum(math.ceil(agem/3 - 65*4),0)
            elig_majo = (trim_RG < P.N_CP)
            trim_corr = trim_RG*(1 + P.tx_maj*trim_majo*elig_majo )
            return trim_corr
        else:
            trim_majo = np.maximum(0, np.ceil(agem/3 - 65*4))
            elig_majo = (trim_tot < P.N_CP)
            trim_corr = trim_RG*(1 + P.tx_maj*trim_majo*elig_majo )
            return trim_corr  
        
    def calculate_coeff_proratisation(self, trim_RG):
        ''' Calcul du coefficient de proratisation '''
        P =  reduce(getattr, self.param_name.split('.'), self.P)
        yearsim = self.yearsim
        N_CP = valbytranches(P.N_CP, self.info_ind)
              
        if 1948 <= yearsim and yearsim < 1972: 
            trim_RG = trim_RG + (120 - trim_RG)/2
        #TODO: voir si on ne met pas cette disposition spécifique de la loi Boulin dans la déclaration des paramètres directement
        elif yearsim < 1973:
            trim_RG = np.min(trim_RG, 128)
        elif yearsim < 1974:
            trim_RG = np.min(trim_RG, 136)            
        elif yearsim < 1975:
            trim_RG = np.min(trim_RG, 144)   
        else:
            trim_RG = np.minimum(N_CP, trim_RG)
        CP = np.minimum(1, trim_RG / N_CP)
        return CP
    
    def decote(self, trim_tot, agem):
        ''' Détermination de la décote à appliquer aux pensions '''
        yearsim = self.yearsim
        P = reduce(getattr, self.param_name.split('.'), self.P)
        tx_decote = valbytranches(P.decote.taux, self.info_ind)
        age_annulation = valbytranches(P.decote.age_null, self.info_ind)
        N_taux = valbytranches(P.plein.N_taux, self.info_ind)
        if yearsim < 1983:
            trim_decote = np.max(0, np.divide(age_annulation - agem, 3))
        else:
            decote_age = np.divide(age_annulation - agem, 3)
            decote_cot = N_taux - trim_tot
            assert len(decote_age) == len(decote_cot)

            trim_decote = np.maximum(0, np.minimum(decote_age, decote_cot))
        return trim_decote*tx_decote
        
    def surcote(self, trim_by_year_tot, trim_maj, agem):
        ''' Détermination de la surcote à appliquer aux pensions '''
        yearsim = self.yearsim
        P = reduce(getattr, self.param_name.split('.'), self.P)
        trim_by_year_RG = self.trim_by_year
        N_taux = valbytranches(P.plein.N_taux, self.info_ind)
        age_min = valbytranches(P.age_min, self.info_ind)

        def _date_surcote(trim_by_year_tot, trim_maj, agem, agemin=age_min, N_t=N_taux, date=self.yearsim):
            ''' Détermine la date individuelle a partir de laquelle il y a surcote ( a atteint l'âge légal de départ en retraite + côtisé le nombre de trimestres cible 
            Rq : pour l'instant on pourrait ne renvoyer que l'année'''
            date_liam = yearsim*100 + 1
            cumul_trim = trim_by_year_tot.array.cumsum(axis=1)
            trim_limit = np.array((N_t - trim_maj.fillna(0)))
            years_surcote = np.greater(cumul_trim.T,trim_limit)
            nb_years_surcote = years_surcote.sum(axis=0)
            #date_cond_trim = (nb_years_surcote).apply(lambda y: date - relativedelta(years = int(y) ))
            #date_cond_age = (agem - agemin).apply(lambda m: date - relativedelta(months = int(m)))
            #return np.maximum(date_cond_age, date_cond_trim)
            date_surcote = [int(max(date_liam - year_surcote*100, 
                                    date_liam - month_trim//12*100 - month_trim%12))
                            for year_surcote, month_trim in zip(nb_years_surcote, agem-agemin)]

            return date_surcote
        
        def _trimestre_surcote_0304(trim_by_year_RG, date_surcote, P):
            ''' surcote associée aux trimestres côtisés en 2003 
            TODO : structure pas approprié pour les réformes du type 'et si on surcotait avant 2003, ça donnerait quoi?'''
            taux_surcote = P.taux_4trim
            trim_selected = trim_by_year_RG.selected_dates(first=2003, last=2004)
            nb_trim = nb_trim_surcote(trim_selected, date_surcote)
            return taux_surcote*nb_trim
        
        def _trimestre_surcote_0408(trim_by_year_RG, trim_by_year_tot, trim_maj, date_surcote, P): 
            ''' Fonction permettant de déterminer la surcote associée des trimestres côtisés entre 2004 et 2008 
            4 premiers à 0.75%, les suivants à 1% ou plus de 65 ans à 1.25% '''
            taux_4trim = P.taux_4trim
            taux_5trim = P.taux_5trim
            taux_65 = P.taux_65
            trim_selected = trim_by_year_RG.selected_dates(first=2004, last=2009)
            #agemin = agem.copy()
            agemin = 65*12 
            date_surcote_65 = _date_surcote(trim_by_year_tot, trim_maj, agem, agemin=agemin)
            nb_trim_65 = nb_trim_surcote(trim_selected, date_surcote_65)
            nb_trim = nb_trim_surcote(trim_selected, date_surcote) 
            nb_trim = nb_trim - nb_trim_65
            return taux_65*nb_trim_65 + taux_4trim*np.maximum(np.minimum(nb_trim,4), 0) + taux_5trim*np.maximum(nb_trim - 4, 0)
        
        def _trimestre_surcote_after_09(trim_by_year_RG, trim_years, date_surcote, P):
            ''' surcote associée aux trimestres côtisés en et après 2009 '''
            taux_surcote = P.taux
            trim_selected = trim_by_year_RG.selected_dates(first=2009, last=None)
            nb_trim = nb_trim_surcote(trim_selected, date_surcote)
            return taux_surcote*nb_trim
            
        date_surcote = _date_surcote(trim_by_year_tot, trim_maj, agem)
        if yearsim < 2004:
            taux_surcote = P.surcote.taux_07
            trim_tot = self.trim_by_year.sum(axis=1)
            return np.maximum(trim_tot - N_taux, 0)*taux_surcote 
        elif yearsim < 2007:
            taux_surcote = P.surcote.taux_07
            trim_surcote = nb_trim_surcote(trim_by_year_RG, date_surcote)
            return trim_surcote*taux_surcote 
        elif yearsim < 2010:
            surcote_03 = _trimestre_surcote_0304(trim_by_year_RG, date_surcote, P.surcote)
            surcote_0408 = _trimestre_surcote_0408(trim_by_year_RG, trim_by_year_tot, trim_maj, date_surcote, P.surcote)
            return surcote_03 + surcote_0408
        else:
            surcote_03 = _trimestre_surcote_0304(trim_by_year_RG, date_surcote, P.surcote)
            surcote_0408 = _trimestre_surcote_0408(trim_by_year_RG, trim_maj, date_surcote, P.surcote)
            surcote_aft09 = _trimestre_surcote_after_09(trim_by_year_RG, date_surcote, P.surcote)
            return surcote_03 + surcote_0408 + surcote_aft09   
        
    def minimum_contributif(self, pension_RG, pension, trim_RG, trim_cot, trim):
        ''' MICO du régime général : allocation différentielle 
        RQ : ASPA et minimum vieillesse sont gérés par OF
        Il est attribué quels que soient les revenus dont dispose le retraité en plus de ses pensions : loyers, revenus du capital, activité professionnelle... 
        + mécanisme de répartition si cotisations à plusieurs régimes'''
        yearsim = self.yearsim
        P = reduce(getattr, self.param_name.split('.'), self.P)
        N_taux = valbytranches(P.plein.N_taux, self.info_ind)
        N_CP = valbytranches(P.N_CP, self.info_ind)
        
        if yearsim < 2004:
            mico = P.mico.entier 
            # TODO: règle relativement complexe à implémenter de la limite de cumul (voir site CNAV)
            return  np.maximum(0, mico - pension_RG)*np.minimum(1, np.divide(trim_cot, N_CP))
        else:
            mico_entier = P.mico.entier
            mico_maj = P.mico.entier_maj
            RG_exclusif = ( pension_RG == pension) | (trim <= N_taux)
            mico_RG = mico_entier + np.minimum(1, np.divide(trim_cot, N_CP))*(mico_maj - mico_entier)
            mico =  mico_RG*( RG_exclusif + (1 - RG_exclusif)*np.divide(trim_RG, trim))
            return np.maximum(0, mico - pension_RG)
        
    def plafond_pension(self, pension_RG, pension_surcote_RG):
        ''' plafonnement à 50% du PSS 
        TODO: gérer les plus de 65 ans au 1er janvier 1983'''
        PSS = self.P.common.plaf_ss
        P = reduce(getattr, self.param_name.split('.'), self.P)
        taux_PSS = P.plafond
        return np.minimum(pension_RG - pension_surcote_RG, taux_PSS*PSS) + pension_surcote_RG
        
            