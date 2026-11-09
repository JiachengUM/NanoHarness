import { useCallback, useEffect, useMemo, useState } from 'react'
import Api from '@/apis/domain-data'
import type { FormItem, FormProps } from '@/components/Form'
import ExForm from '@/components/Form'
import { Radio } from 'antd'
import { DOMAIN_FORM_TYPE_OPTIONS, SHOW_HIDDEN_OPTIONS } from '@/constants'

const defaultForm: VehicleState = {}

type Props = {
  formData?: VehicleState
  onSuccess?: () => void
  onCancel?: () => void
}

const App = (props: Props) => {
  const [formData, setFormData] = useState<VehicleState>(defaultForm)
  const [editType, setEditType] = useState<string>('json')
  const [showMap, setShowMap] = useState<Record<string, boolean>>({
    adsd: true,
    media: true,
    navigation: true,
    signal_light: true,
    system_control: true,
    vehicle_control: true,
  })

  const getTitleChildren = useCallback(
    (key: string, label: string) => {
      return (
        <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
          <b style={{ width: 100, textAlign: 'left' }}>{label}</b>
          <Radio.Group
            value={showMap[key]}
            options={SHOW_HIDDEN_OPTIONS}
            size="small"
            optionType="button"
            buttonStyle="solid"
            onChange={(e) => setShowMap((prev) => ({ ...prev, [key]: e.target.value }))}
          />
        </div>
      )
    },
    [showMap]
  )

  const formList: FormItem[] = useMemo(() => {
    const list: FormItem[] = [
      {
        label: '摘要信息',
        name: 'brief',
        type: 'input',
        required: true,
      },
      {
        label: '',
        name: 'entity-title',
        type: 'title',
        children: (
          <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
            <b>实体信息</b>
            <Radio.Group
              value={editType}
              options={DOMAIN_FORM_TYPE_OPTIONS}
              size="small"
              optionType="button"
              buttonStyle="solid"
              onChange={(e) => setEditType(e.target.value)}
            />
          </div>
        ),
      },
    ]

    const jsonFormList: FormItem[] = [
      {
        label: '实体信息',
        name: 'entity',
        type: 'json',
      },
    ]

    const adsdFormList: FormItem[] = [
      { label: '自适应巡航', name: ['entity', 'adsd', 'adaptive_cruise'], type: 'json' },
      { label: '全速驾驶辅助', name: ['entity', 'adsd', 'full_speed_driving_assist'], type: 'json' },
      { label: '领航辅助', name: ['entity', 'adsd', 'pilot_assist'], type: 'json' },
      { label: '变道确认开关', name: ['entity', 'adsd', 'lane_change_confirm'], type: 'json' },
      { label: '信任增强开关', name: ['entity', 'adsd', 'trust_enhance'], type: 'json' },
      { label: '开放道路NOA', name: ['entity', 'adsd', 'open_road_noa'], type: 'json' },
      { label: 'Pilot全速驾驶辅助', name: ['entity', 'adsd', 'pilot_full_speed'], type: 'json' },
      { label: '指令自动变道CALC', name: ['entity', 'adsd', 'calc_lane_change'], type: 'json' },
      { label: '智驾风格选项', name: ['entity', 'adsd', 'driving_style'], type: 'json' },
      { label: '起步提醒选项开关', name: ['entity', 'adsd', 'start_reminder'], type: 'json' },
      { label: '限速调整区间', name: ['entity', 'adsd', 'speed_limit_range'], type: 'json' },
      { label: '限速调整固定速度', name: ['entity', 'adsd', 'speed_limit_fixed'], type: 'json' },
      { label: '限速百分比调整', name: ['entity', 'adsd', 'speed_limit_percent'], type: 'json' },
      { label: '限速报警', name: ['entity', 'adsd', 'speed_limit_alarm'], type: 'json' },
      { label: '前向碰撞预警', name: ['entity', 'adsd', 'forward_collision_warning'], type: 'json' },
      { label: '前向碰撞预警灵敏度', name: ['entity', 'adsd', 'fcw_sensitivity'], type: 'json' },
      { label: '自动紧急制动', name: ['entity', 'adsd', 'aeb'], type: 'json' },
      { label: '后向碰撞预警', name: ['entity', 'adsd', 'rear_collision_warning'], type: 'json' },
      { label: '盲点预警', name: ['entity', 'adsd', 'blind_spot_warning'], type: 'json' },
      { label: '后侧方来车预警', name: ['entity', 'adsd', 'rear_cross_traffic'], type: 'json' },
      { label: '开门预警', name: ['entity', 'adsd', 'door_open_warning'], type: 'json' },
      { label: '车道偏离辅助', name: ['entity', 'adsd', 'lane_departure_assist'], type: 'json' },
      { label: '车道偏离辅助预警灵敏度', name: ['entity', 'adsd', 'lda_sensitivity'], type: 'json' },
      { label: '车道偏离预警警示方式', name: ['entity', 'adsd', 'ldw_alert_mode'], type: 'json' },
      { label: '车道保持辅助', name: ['entity', 'adsd', 'lane_keep'], type: 'json' },
    ]

    const mediaFormList: FormItem[] = [
      { label: '音频信号', name: ['entity', 'media', 'audio_signal'], type: 'json' },
      { label: '视频信号', name: ['entity', 'media', 'video_signal'], type: 'json' },
    ]

    const navigationFormList: FormItem[] = [
      { label: '导航状态', name: ['entity', 'navigation', 'navigation_status'], type: 'json' },
      { label: '目的地', name: ['entity', 'navigation', 'destination'], type: 'json' },
      { label: '目的地类型', name: ['entity', 'navigation', 'destination_type'], type: 'json' },
      { label: '目的地信息', name: ['entity', 'navigation', 'destination_info'], type: 'json' },
      { label: '路况', name: ['entity', 'navigation', 'road_condition'], type: 'json' },
      { label: '严重拥堵', name: ['entity', 'navigation', 'heavy_traffic'], type: 'json' },
      { label: '途径点', name: ['entity', 'navigation', 'waypoint'], type: 'json' },
      { label: '服务区', name: ['entity', 'navigation', 'service_area'], type: 'json' },
    ]

    const signalLightFormList: FormItem[] = [
      { label: '近光灯', name: ['entity', 'signal_light', 'low_beam'], type: 'json' },
      { label: '远光灯', name: ['entity', 'signal_light', 'high_beam'], type: 'json' },
      { label: '远光灯开关', name: ['entity', 'signal_light', 'high_beam_switch'], type: 'json' },
      { label: '后雾灯', name: ['entity', 'signal_light', 'rear_fog_light'], type: 'json' },
      { label: '位置灯', name: ['entity', 'signal_light', 'position_light'], type: 'json' },
      { label: '左转向灯', name: ['entity', 'signal_light', 'left_turn_signal'], type: 'json' },
      { label: '右转向灯', name: ['entity', 'signal_light', 'right_turn_signal'], type: 'json' },
      { label: '智能大灯', name: ['entity', 'signal_light', 'intelligent_headlight'], type: 'json' },
      { label: 'AFS故障', name: ['entity', 'signal_light', 'afs_fault'], type: 'json' },
      { label: 'ABS故障', name: ['entity', 'signal_light', 'abs_fault'], type: 'json' },
      { label: '制动故障', name: ['entity', 'signal_light', 'brake_fault'], type: 'json' },
      { label: 'ESP故障', name: ['entity', 'signal_light', 'esp_fault'], type: 'json' },
      { label: 'ESP工作状态', name: ['entity', 'signal_light', 'esp_working'], type: 'json' },
      { label: 'TCS故障', name: ['entity', 'signal_light', 'tcs_fault'], type: 'json' },
      { label: '自动驻车激活', name: ['entity', 'signal_light', 'autohold_active'], type: 'json' },
      { label: '自动驻车待命', name: ['entity', 'signal_light', 'autohold_ready'], type: 'json' },
      { label: 'Autohold故障', name: ['entity', 'signal_light', 'autohold_fault'], type: 'json' },
      { label: '四驱系统', name: ['entity', 'signal_light', 'four_wheel_drive'], type: 'json' },
      { label: '胎压异常', name: ['entity', 'signal_light', 'tire_pressure_warning'], type: 'json' },
      { label: '胎压系统故障', name: ['entity', 'signal_light', 'tire_pressure_fault'], type: 'json' },
      { label: '充电系统故障', name: ['entity', 'signal_light', 'charging_fault'], type: 'json' },
      { label: '辅助系统供电故障', name: ['entity', 'signal_light', 'auxiliary_power_fault'], type: 'json' },
      { label: '安全气囊故障', name: ['entity', 'signal_light', 'airbag_fault'], type: 'json' },
      { label: '安全气囊未标定', name: ['entity', 'signal_light', 'airbag_uncalibrated'], type: 'json' },
      { label: '第一排安全带未系提醒', name: ['entity', 'signal_light', 'front_seatbelt_warning'], type: 'json' },
      { label: '第二排安全带未系提示', name: ['entity', 'signal_light', 'rear_seatbelt_warning'], type: 'json' },
      { label: '行人保护提醒', name: ['entity', 'signal_light', 'pedestrian_protection_warning'], type: 'json' },
      { label: '转向故障', name: ['entity', 'signal_light', 'steering_fault'], type: 'json' },
      { label: '方向盘角度故障', name: ['entity', 'signal_light', 'steering_angle_fault'], type: 'json' },
      { label: 'ESCL故障', name: ['entity', 'signal_light', 'escl_fault'], type: 'json' },
      { label: '转向降低', name: ['entity', 'signal_light', 'steering_reduced'], type: 'json' },
      { label: 'EPB指示', name: ['entity', 'signal_light', 'epb_indicator'], type: 'json' },
      { label: 'EPB未释放', name: ['entity', 'signal_light', 'epb_not_released'], type: 'json' },
      { label: 'EPB故障', name: ['entity', 'signal_light', 'epb_fault'], type: 'json' },
      { label: '钥匙不在车内/防盗', name: ['entity', 'signal_light', 'key_warning'], type: 'json' },
      { label: '动力电池故障', name: ['entity', 'signal_light', 'power_battery_fault'], type: 'json' },
      { label: '动力电池电量', name: ['entity', 'signal_light', 'power_battery_level'], type: 'json' },
      { label: '动力电池电量低', name: ['entity', 'signal_light', 'power_battery_low'], type: 'json' },
      { label: '充放电枪连接', name: ['entity', 'signal_light', 'charge_gun_connected'], type: 'json' },
      { label: '充电中', name: ['entity', 'signal_light', 'charging'], type: 'json' },
      { label: '充放电故障', name: ['entity', 'signal_light', 'charge_discharge_fault'], type: 'json' },
      { label: '放电中', name: ['entity', 'signal_light', 'discharging'], type: 'json' },
      { label: '挡位信号无效', name: ['entity', 'signal_light', 'gear_invalid'], type: 'json' },
      { label: '系统就绪', name: ['entity', 'signal_light', 'system_ready'], type: 'json' },
      { label: '系统故障', name: ['entity', 'signal_light', 'system_fault'], type: 'json' },
      { label: '功率受限', name: ['entity', 'signal_light', 'power_limited'], type: 'json' },
      { label: '电机故障', name: ['entity', 'signal_light', 'motor_fault'], type: 'json' },
      { label: '空气悬架故障', name: ['entity', 'signal_light', 'air_suspension_fault'], type: 'json' },
      { label: 'Ecall状态', name: ['entity', 'signal_light', 'ecall_status'], type: 'json' },
      { label: '后轮转向故障', name: ['entity', 'signal_light', 'rear_wheel_steering_fault'], type: 'json' },
      { label: '危险报警灯', name: ['entity', 'signal_light', 'hazard_warning'], type: 'json' },
      { label: '氛围灯', name: ['entity', 'signal_light', 'ambient_light'], type: 'json' },
      { label: '阅读灯', name: ['entity', 'signal_light', 'reading_light'], type: 'json' },
    ]

    const systemControlFormList: FormItem[] = [
      { label: '保养信息', name: ['entity', 'system_control', 'maintenance_info'], type: 'json' },
      { label: '显示模式', name: ['entity', 'system_control', 'display_mode'], type: 'json' },
      { label: '乘客信息', name: ['entity', 'system_control', 'passenger_info'], type: 'json' },
    ]

    const vehicleControlFormList: FormItem[] = [
      { label: '驾驶模式', name: ['entity', 'vehicle_control', 'driving_mode'], type: 'json' },
      { label: '车速', name: ['entity', 'vehicle_control', 'vehicle_speed'], type: 'json' },
      { label: '能量回收', name: ['entity', 'vehicle_control', 'energy_recovery'], type: 'json' },
      { label: '档位', name: ['entity', 'vehicle_control', 'gear'], type: 'json' },
      { label: '再生制动', name: ['entity', 'vehicle_control', 'regenerative_braking'], type: 'json' },
      { label: '轮胎信息', name: ['entity', 'vehicle_control', 'tire_info'], type: 'json' },
      { label: '充电盖', name: ['entity', 'vehicle_control', 'charging_port'], type: 'json' },
      { label: '充电状态', name: ['entity', 'vehicle_control', 'charging_status'], type: 'json' },
      { label: '充电限制', name: ['entity', 'vehicle_control', 'charging_limit'], type: 'json' },
      { label: '电池信息', name: ['entity', 'vehicle_control', 'battery_info'], type: 'json' },
      { label: '空调状态', name: ['entity', 'vehicle_control', 'air_condition'], type: 'json' },
      { label: '空调风向', name: ['entity', 'vehicle_control', 'air_direction'], type: 'json' },
      { label: '空调循环模式', name: ['entity', 'vehicle_control', 'air_circulation'], type: 'json' },
      { label: '空调制冷', name: ['entity', 'vehicle_control', 'air_cooling'], type: 'json' },
      { label: '除霜除雾', name: ['entity', 'vehicle_control', 'defrost_defog'], type: 'json' },
      { label: '空气净化', name: ['entity', 'vehicle_control', 'air_purification'], type: 'json' },
      { label: '前排风量', name: ['entity', 'vehicle_control', 'fan_speed_front'], type: 'json' },
      { label: '后排风量', name: ['entity', 'vehicle_control', 'fan_speed_rear'], type: 'json' },
      { label: '车内温度', name: ['entity', 'vehicle_control', 'interior_temperature'], type: 'json' },
      { label: '座椅位置', name: ['entity', 'vehicle_control', 'seat_position'], type: 'json' },
      { label: '座椅通风', name: ['entity', 'vehicle_control', 'seat_ventilation'], type: 'json' },
      { label: '座椅加热', name: ['entity', 'vehicle_control', 'seat_heating'], type: 'json' },
      { label: '座椅按摩', name: ['entity', 'vehicle_control', 'seat_massage'], type: 'json' },
      { label: '安全带状态', name: ['entity', 'vehicle_control', 'seat_belt_status'], type: 'json' },
      { label: '车窗状态', name: ['entity', 'vehicle_control', 'window_status'], type: 'json' },
      { label: '车门状态', name: ['entity', 'vehicle_control', 'door_status'], type: 'json' },
      { label: '左后遮阳帘', name: ['entity', 'vehicle_control', 'sunshade_left_rear'], type: 'json' },
      { label: '右后遮阳帘', name: ['entity', 'vehicle_control', 'sunshade_right_rear'], type: 'json' },
      { label: '后视镜状态', name: ['entity', 'vehicle_control', 'rearview_mirror'], type: 'json' },
      { label: '雨刮状态', name: ['entity', 'vehicle_control', 'wiper_status'], type: 'json' },
      { label: '方向盘加热', name: ['entity', 'vehicle_control', 'steering_wheel_heating'], type: 'json' },
      { label: '香氛系统', name: ['entity', 'vehicle_control', 'fragrance_system'], type: 'json' },
      { label: '音量状态', name: ['entity', 'vehicle_control', 'volume_status'], type: 'json' },
      { label: '天窗状态', name: ['entity', 'vehicle_control', 'sunroof_status'], type: 'json' },
      { label: '尾门状态', name: ['entity', 'vehicle_control', 'tailgate_status'], type: 'json' },
      { label: '雷达状态', name: ['entity', 'vehicle_control', 'radar_status'], type: 'json' },
      { label: '360全景影像', name: ['entity', 'vehicle_control', 'panoramic_camera'], type: 'json' },
      { label: '日历时间', name: ['entity', 'vehicle_control', 'calendar_time'], type: 'json' },
      { label: '自动泊车', name: ['entity', 'vehicle_control', 'auto_parking'], type: 'json' },
    ]

    const entityFormList: FormItem[] = [
      { label: '', name: ['entity', 'adsd'], type: 'title', children: getTitleChildren('adsd', 'ADSD状态') },
      ...(showMap['adsd'] ? adsdFormList : []),
      { label: '', name: ['entity', 'media'], type: 'title', children: getTitleChildren('media', '多媒体状态') },
      ...(showMap['media'] ? mediaFormList : []),
      {
        label: '',
        name: ['entity', 'navigation'],
        type: 'title',
        children: getTitleChildren('navigation', '导航状态'),
      },
      ...(showMap['navigation'] ? navigationFormList : []),
      {
        label: '',
        name: ['entity', 'signal_light'],
        type: 'title',
        children: getTitleChildren('signal_light', '信号灯状态'),
      },
      ...(showMap['signal_light'] ? signalLightFormList : []),
      {
        label: '',
        name: ['entity', 'system_control'],
        type: 'title',
        children: getTitleChildren('system_control', '系统控制状态'),
      },
      ...(showMap['system_control'] ? systemControlFormList : []),
      {
        label: '',
        name: ['entity', 'vehicle_control'],
        type: 'title',
        children: getTitleChildren('vehicle_control', '车辆控制状态'),
      },
      ...(showMap['vehicle_control'] ? vehicleControlFormList : []),
      { label: '其它状态', name: ['entity', 'more_states_title'], type: 'title' },
      { label: '其它状态', name: ['entity', 'more_states'], type: 'json' },
    ]

    if (editType === 'json') return [...list, ...jsonFormList]
    if (editType === 'form') return [...list, ...entityFormList]
    return list
  }, [editType, getTitleChildren, showMap])

  useEffect(() => {
    setFormData(props.formData || defaultForm)
  }, [props.formData])

  const formpProps: FormProps<VehicleState> = {
    formList,
    formData,
    setFormData,
    labelWidth: 100,
    createApi: Api.vehicleState.create,
    updateApi: Api.vehicleState.update,
    onCancel: props.onCancel,
    onSuccess: props.onSuccess,
  }

  return (
    <>
      <ExForm<VehicleState> {...formpProps} />
    </>
  )
}

export default App
