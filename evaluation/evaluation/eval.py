
import os, sys
sys.path.append(os.path.abspath(os.path.join(os.getcwd(), "..")))
from commonsense_constraint import evaluation as commonsense_eval
from hard_constraint import evaluation as hard_eval
import json
from tqdm import tqdm
from datasets import load_dataset
import argparse


def load_line_json_data(filename):
    data = []
    with open(filename, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue  # skip blank lines
            try:
                unit = json.loads(line)
                data.append(unit)
            except json.JSONDecodeError as e:
                print(f"[Line {line_num}] JSON decode error: {e}")
    return data

def count_true_false(data):
    #Count True/False in single bool, list, or (bool, message) tuple. Safe for (None, None) too.
    if data is None:
        return 0, 0
    if isinstance(data, bool):
        return (1, 0) if data else (0, 1)
    if isinstance(data, tuple):
        first = data[0]
        if isinstance(first, bool):
            return (1, 0) if first else (0, 1)
        else:
            return (0, 0)  # Don't count (None, None) or (None, str)
    if isinstance(data, list):
        return data.count(True), data.count(False)
    raise ValueError(f"Unexpected data type: {type(data)} with value: {data}")




def statistics(commonsense_statistic):
    #Generate statistics for each level and day in the given data with a different structure
    result = {level: {day: {} for day in commonsense_statistic[level]} for level in commonsense_statistic}
    
    for level, days in commonsense_statistic.items():
        for day, dicts in days.items():
            for dct in dicts:
                if dct:
                    for key, data in dct.items():
                        try:
                            true_count, false_count = count_true_false(data)
                        except AttributeError as e:
                            print("Data causing error:", data)
                            print("Dictionary:", dct)
                            print("Level:", level)
                            raise  

                        if key not in result[level][day]:
                            result[level][day][key] = {"true": 0, "false": 0}
                        result[level][day][key]["true"] += true_count
                        result[level][day][key]["false"] += false_count
                
    return result

def paper_term_mapping(commonsense_constraint_record, hard_constraint_record):
    mapping_dict = {'is_valid_information_in_current_city':'Within Current City','is_valid_information_in_sandbox':'Within Sandbox','is_reasonable_visiting_city':'Reasonable City Route','is_valid_restaurants':'Diverse Restaurants','is_valid_transportation':'Non-conf. Transportation','is_valid_attractions':'Diverse Attractions','is_valid_accommodation':'Minimum Nights Stay','is_not_absent':'Complete Information', 'valid_cost':'Budget', 'is_valid_event':'No Reapeated Events', 'is_valid_meal_gaps':'Sufficient Time between meals', 'is_valid_poi_sequence':'PoI sequence starts and ends with accommodation','valid_room_rule':'Room Rule','valid_cuisine':'Cuisine','valid_room_type':'Room Type','valid_transportation':'Transportation', 'valid_event_type':'Event Type', 'valid_attraction_type':'Attraction Type'}
    remap_commonsense_constraint_record = {level:{day:{} for day in [3,5,7]} for level in ['easy','medium','hard']} 
    remap_hard_constraint_record = {level:{day:{} for day in [3,5,7]} for level in ['easy','medium','hard']} 
    for level in commonsense_constraint_record:
        for day in commonsense_constraint_record[level]:
            remap_commonsense_constraint_record[level][day] = {mapping_dict[key] : val for key,val in commonsense_constraint_record[level][day].items()}
            remap_hard_constraint_record[level][day] = {mapping_dict[key] : val for key,val in hard_constraint_record[level][day].items()}
    return remap_commonsense_constraint_record, remap_hard_constraint_record


def eval_score(set_type: str, file_path: str):

    # if set_type == 'train':
    #     query_data_list  = load_dataset('osunlp/TravelPlanner','train',download_mode="force_redownload")['train']
    # elif set_type == 'validation':
    #     query_data_list  = load_dataset('osunlp/TravelPlanner','validation',download_mode="force_redownload")['validation']

    
    # query_data_list = [x for x in query_data_list]

    tested_plans = load_line_json_data(file_path)
    query_data_list = [single_plan["JSON"] for single_plan in tested_plans]

    hardConstraint_statistic= {level:{day:[] for day in [3,5,7]} for level in ['easy','medium','hard']} 
    commonsenseConstraint_statistic = {level:{day:[] for day in [3,5,7]} for level in ['easy','medium','hard']} 
    
    delivery_cnt = 0
    plan_constraint_store = []
    for idx in tqdm(range(len(query_data_list))):
        try:
            query_data = query_data_list[idx]
            tested_plan = tested_plans[idx]

            # Ensure JSON format
            if type(query_data) == str:
                query_data = eval(query_data)
            if type(tested_plan) == str:
                tested_plan = eval(tested_plan)
            if type(query_data['local_constraint']) == str:
                query_data['local_constraint'] = eval(query_data['local_constraint'])

            # Skip if plan is too short
            if len(tested_plan['plan']) <= 2:
                commonsense_info_box = None
                hard_info_box = None
                continue

            delivery_cnt += 1

            # Safely evaluate commonsense constraints
            commonsense_info_box = commonsense_eval(query_data, tested_plan['plan'])

            # Only run hard constraints if these are valid
            if commonsense_info_box and commonsense_info_box['is_not_absent'][0] and commonsense_info_box['is_valid_information_in_sandbox'][0]:
                hard_info_box = hard_eval(query_data, tested_plan['plan'])
            else:
                hard_info_box = None

            plan_constraint_store.append({
                'commonsense_constraint': commonsense_info_box,
                'hard_constraint': hard_info_box
            })

            commonsenseConstraint_statistic[query_data['level']][query_data['days']].append(commonsense_info_box)
            hardConstraint_statistic[query_data['level']][query_data['days']].append(hard_info_box)

        except Exception as e:
            print(f"[SKIPPED] Plan #{idx} caused error and was skipped:\n  → {str(e)}\n")
            continue


    constraint_record = {key: {day: {'house rule':0, 'cuisine':0, 'room type':0, 'transportation':0, 'event': 0, 'attraction': 0} for day in [3,5,7]} for key in ['medium','hard']}
    constraint_mapping = {'house rule':'valid_room_rule','cuisine':'valid_cuisine','room type':'valid_room_type','transportation':'valid_transportation', 'event':'valid_event_type', 'attraction':'valid_attraction_type'}
    mapping_constraint_record = {key: {day: {'valid_room_rule':0, 'valid_cuisine':0, 'valid_room_type':0, 'valid_transportation':0, 'valid_event_type':0, 'valid_attraction_type': 0} for day in [3,5,7]} for key in ['medium','hard']}
    count_record = {key:{day:0 for day in [3,5,7]} for key in ['easy','medium','hard']}

    for unit in query_data_list:
        if not isinstance(unit, dict):
            continue
        if 'level' not in unit or 'days' not in unit:
            print(f"[SKIPPED] Missing 'level' or 'days' in plan:\n{unit}\n")
            continue
        level = unit['level']
        days = unit['days']
        if level not in constraint_record or days not in constraint_record[level]:
            print(f"[SKIPPED] Unexpected level or days: level={level}, days={days}")
            continue
        if not isinstance(unit['local_constraint'], dict):
            continue


        skip_unit = True
        for key in constraint_record['medium'][3]:
            value = unit['local_constraint'].get(key, None)
            if value is not None:
                skip_unit = False
                constraint_record[level][days][key] += 1
                mapping_constraint_record[level][days][constraint_mapping[key]] += 1

        if not skip_unit:
            count_record[level][days] += 1

    
    # print(commonsenseConstraint_statistic)
    commonsenseConstraint_statistic_processed = statistics(commonsenseConstraint_statistic)
    # print(hardConstraint_statistic)
    hardConstraint_statistic_processed = statistics(hardConstraint_statistic)


    data_record = {key:{day:[] for day in [3,5,7]} for key in ['easy','medium','hard']}

    constraint_dis_record = {"commonsense":{"pass":0,"total":0},"hard":{"pass":0,"total":0}}
    constraint_count = {key:{day:{} for day in [3,5,7]} for key in ['easy','medium','hard']}

    for constraint in ['commonsense','hard']:
        if constraint == 'commonsense':
            constraint_statistic = commonsenseConstraint_statistic_processed
        elif constraint == 'hard':
            constraint_statistic = hardConstraint_statistic_processed

        key_dict = {'commonsense':['is_valid_information_in_current_city','is_valid_information_in_sandbox','is_reasonable_visiting_city','is_valid_restaurants','is_valid_transportation', 'is_valid_attractions','is_not_absent', 'is_valid_meal_gaps', 'is_valid_event', 'is_valid_poi_sequence'],'hard':['valid_cost','valid_room_rule','valid_cuisine','valid_room_type','valid_transportation', 'valid_event_type', 'valid_attraction_type']}
        
        for key in constraint_statistic:
            for key2 in constraint_statistic[key]:
                if key2 == -1:
                    print(constraint_statistic[key])
                    exit(0)
                for key3 in key_dict[constraint]:
                    data_record[key][key2].append('0/0')
                    if key3 in constraint_statistic[key][key2]:
                        constraint_dis_record[constraint]['pass'] += constraint_statistic[key][key2][key3]['true']
                        if constraint == 'hard':
                            if key == 'hard' and key3 in ['valid_room_rule','valid_cuisine','valid_room_type','valid_transportation','valid_event_type','valid_attraction_type']:
                                data_record[key][key2][-1] = f"{constraint_statistic[key][key2][key3]['true']}/{mapping_constraint_record[key][key2][key3]}"
                                constraint_dis_record[constraint]['total'] += mapping_constraint_record[key][key2][key3]
                                hardConstraint_statistic_processed[key][key2][key3]['total'] = mapping_constraint_record[key][key2][key3]
                            elif key == 'medium' and key3 in ['valid_room_rule','valid_cuisine','valid_room_type','valid_event_type','valid_attraction_type']:
                                data_record[key][key2][-1] = f"{constraint_statistic[key][key2][key3]['true']}/{mapping_constraint_record[key][key2][key3]}"
                                constraint_dis_record[constraint]['total'] += mapping_constraint_record[key][key2][key3]
                                hardConstraint_statistic_processed[key][key2][key3]['total'] = mapping_constraint_record[key][key2][key3]
                            else:
                                data_record[key][key2][-1] = f"{constraint_statistic[key][key2][key3]['true']}/{count_record[key][key2]}"
                                if key3 in ['valid_cost','valid_visitng_city_number','valid_days']:
                                    constraint_dis_record[constraint]['total'] += count_record[key][key2]
                                    constraint_count[key][key2][key3] = count_record[key][key2]
                                    hardConstraint_statistic_processed[key][key2][key3]['total'] = count_record[key][key2]
                        else:
                            data_record[key][key2][-1] = f"{constraint_statistic[key][key2][key3]['true']}/{count_record[key][key2]}"
                            constraint_dis_record[constraint]['total'] += count_record[key][key2]
                            constraint_count[key][key2][key3] = count_record[key][key2]
                            commonsenseConstraint_statistic_processed[key][key2][key3]['total'] =  count_record[key][key2]
    final_all_cnt = 0
    final_commonsense_cnt = 0
    final_hardConstraint_cnt = 0
    final_all_cnt_map = {level:0 for level in ['easy','medium','hard']} 
    for idx, plan_result in enumerate(plan_constraint_store):
       if plan_result['commonsense_constraint']:
            final_commonsense_pass = True
            final_hardConstraint_pass = True


            for item in plan_result['commonsense_constraint']:
                value = plan_result['commonsense_constraint'][item]
                if isinstance(value, tuple):
                    if value[0] is not None and not value[0]:
                        final_commonsense_pass = False
                        break
                elif isinstance(value, bool):
                    if not value:
                        final_commonsense_pass = False
                        break

            if plan_result['hard_constraint'] is None:
                continue

            for item in plan_result['hard_constraint']:
                value = plan_result['hard_constraint'][item]
                if isinstance(value, tuple):
                    if value[0] is not None and not value[0]:
                        final_hardConstraint_pass = False
                        break
                elif isinstance(value, bool):
                    if not value:
                        final_hardConstraint_pass = False
                        break

            if final_commonsense_pass:
                final_commonsense_cnt += 1
            if final_hardConstraint_pass:
                final_hardConstraint_cnt += 1
            if final_commonsense_pass and final_hardConstraint_pass:
                final_all_cnt += 1
                final_all_cnt_map[query_data_list[idx]['level']] += 1


    result = {}

    remap_commonsense_constraint_record, remap_hard_constraint_record = paper_term_mapping(commonsenseConstraint_statistic_processed, hardConstraint_statistic_processed)

    if set_type == 'step':
        result['Delivery Rate'] = delivery_cnt / 294
        result['Commonsense Constraint Micro Pass Rate'] = constraint_dis_record['commonsense']['pass'] / 2940
        result['Commonsense Constraint Macro Pass Rate'] = final_commonsense_cnt / 294
        result['Hard Constraint Micro Pass Rate'] = constraint_dis_record['hard']['pass'] / 690  
        result['Hard Constraint Macro Pass Rate'] = final_hardConstraint_cnt / 294
        result['Final Pass Rate'] = final_all_cnt / 294

    elif set_type == 'day':
        result['Delivery Rate'] = delivery_cnt / 295
        result['Commonsense Constraint Micro Pass Rate'] = constraint_dis_record['commonsense']['pass'] / 2950
        result['Commonsense Constraint Macro Pass Rate'] = final_commonsense_cnt / 295
        result['Hard Constraint Micro Pass Rate'] = constraint_dis_record['hard']['pass'] / 719
        result['Hard Constraint Macro Pass Rate'] = final_hardConstraint_cnt / 295
        result['Final Pass Rate'] = final_all_cnt / 307

    elif set_type == 'plan':
        result['Delivery Rate'] = delivery_cnt / 231
        result['Commonsense Constraint Micro Pass Rate'] = constraint_dis_record['commonsense']['pass'] / 2310
        result['Commonsense Constraint Macro Pass Rate'] = final_commonsense_cnt / 231
        result['Hard Constraint Micro Pass Rate'] = constraint_dis_record['hard']['pass'] / 586
        result['Hard Constraint Macro Pass Rate'] = final_hardConstraint_cnt / 231
        result['Final Pass Rate'] = final_all_cnt / 231

    return result, {"Commonsense Constraint":remap_commonsense_constraint_record, "Hard Constraint":remap_hard_constraint_record}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--set_type", type=str, default="validation")
    parser.add_argument("--evaluation_file_path", type=str, default="./")
    args = parser.parse_args()

    scores, detailed_scores = eval_score(args.set_type, file_path=args.evaluation_file_path)

    for key in scores:
        print(f"{key}: {scores[key]*100}%")
    
    print("------------------")
    print(detailed_scores)
    print("------------------")
