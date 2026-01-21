import cv2
import mediapipe as mp
import math
import time

# Set up camera and MediaPipe hands
cap = cv2.VideoCapture(0)
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(max_num_hands=1, min_detection_confidence=0.7, min_tracking_confidence=0.7)
mp_draw = mp.solutions.drawing_utils

# Helper to measure distance between two points
def get_dist(p1, p2):
    return math.hypot(p2[0] - p1[0], p2[1] - p1[1])

# Helper to map a number from one range to another
def map_range(value, in_min, in_max, out_min, out_max):
    return out_min + (float(value - in_min) / float(in_max - in_min) * (out_max - out_min))

# Calculate the angle between three points, ignoring hand rotation
def get_angle(p1, p2, p3):
    a1 = math.atan2(p1[1] - p2[1], p1[0] - p2[0])
    a2 = math.atan2(p3[1] - p2[1], p3[0] - p2[0])
    deg = math.degrees(a1 - a2)
    deg = abs(deg)
    if deg > 180: deg = 360 - deg
    return deg

# Convert raw geometric angles to realistic biomechanical limits
def get_biomechanical_angle(p1, p2, p3, min_limit=50, max_limit=180):
    theta_raw = get_angle(p1, p2, p3)
    theta_bio = map_range(theta_raw, 0, 180, min_limit, max_limit)
    return max(min_limit, min(max_limit, theta_bio))

p_time = 0

while True:
    success, img = cap.read()
    if not success: break
    
    # Flip the image for a mirror effect
    img = cv2.flip(img, 1)
    h, w, c = img.shape
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    res = hands.process(img_rgb)

    cv2.putText(img, "MCP: Y-Distance Mapping", (10, 30), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 200, 0), 2)

    if res.multi_hand_landmarks:
        for hand_lms in res.multi_hand_landmarks:
            lm = []
            for id, l in enumerate(hand_lms.landmark):
                lm.append((int(l.x * w), int(l.y * h)))

            # Measure hand size so the logic works at any distance
            hand_scale = get_dist(lm[0], lm[9])

            # Calculate MCP (Knuckle) angles based on vertical distance to PIP
            # If the PIP is far above the MCP, the hand is open. If close, it's closed.
            mcp_joints = [
                ("I_MCP", 5, 6),
                ("M_MCP", 9, 10),
                ("R_MCP", 13, 14),
                ("P_MCP", 17, 18)
            ]
            
            pip_angles = {} 

            for name, m_id, p_id in mcp_joints:
                y_diff = lm[m_id][1] - lm[p_id][1]
                
                # Set thresholds for open vs closed based on hand size
                open_thresh = hand_scale * 0.5
                closed_thresh = hand_scale * 0.1

                # Map the distance to an angle between 55 and 180
                theta = map_range(y_diff, closed_thresh, open_thresh, 55, 180)
                theta = max(55, min(180, theta))
                
                cv2.putText(img, f"{int(theta)}", (lm[m_id][0] - 10, lm[m_id][1] + 15), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

            # Calculate PIP (Middle Joint) angles using standard geometry
            pip_joints = [
                ("I_PIP", 5, 6, 7),
                ("M_PIP", 9, 10, 11),
                ("R_PIP", 13, 14, 15),
                ("P_PIP", 17, 18, 19)
            ]

            for name, m_id, p_id, d_id in pip_joints:
                theta = get_biomechanical_angle(lm[m_id], lm[p_id], lm[d_id], min_limit=50, max_limit=180)
                pip_angles[name[0]] = theta 
                
                cv2.putText(img, f"{int(theta)}", (lm[p_id][0] + 15, lm[p_id][1]), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)

            # Handle the thumb separately since its joints move differently
            t_mcp = get_biomechanical_angle(lm[1], lm[2], lm[3], 50, 180)
            t_ip = get_biomechanical_angle(lm[2], lm[3], lm[4], 50, 180)
            cv2.putText(img, f"{int(t_mcp)}", (lm[2][0]+10, lm[2][1]), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0,0,255), 1)
            cv2.putText(img, f"{int(t_ip)}", (lm[3][0]+10, lm[3][1]), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255,0,0), 1)

            # Estimate DIP angles based on the PIP angle
            dip_map = {'I': 7, 'M': 11, 'R': 15, 'P': 19}
            for char, pip_val in pip_angles.items():
                dip_val = map_range(pip_val, 50, 180, 80, 180)
                idx = dip_map[char]
                cv2.putText(img, f"{int(dip_val)}", (lm[idx][0] + 10, lm[idx][1]), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)

            # Calculate Splay (spread) by checking deviation from a resting angle
            splays = [
                ("Idx", 5,  9,  6,  80), 
                ("Mid", 9,  13, 10, 85), 
                ("Rng", 13, 9,  14, 85), 
                ("Pky", 17, 13, 18, 85) 
            ]
            
            for name, vert, ref, tip, rest in splays:
                raw_angle = get_angle(lm[ref], lm[vert], lm[tip])
                splay = abs(raw_angle - rest)
                if splay < 4: splay = 0
                
                vx, vy = lm[vert]
                cv2.putText(img, f"S:{int(splay)}", (vx - 20, vy + 45), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 255), 1)

            mp_draw.draw_landmarks(img, hand_lms, mp_hands.HAND_CONNECTIONS)

    c_time = time.time()
    fps = 1 / (c_time - p_time) if (c_time - p_time) > 0 else 0
    p_time = c_time
    cv2.putText(img, f"FPS: {int(fps)}", (10, 70), cv2.FONT_HERSHEY_PLAIN, 2, (0, 255, 0), 2)

    cv2.imshow("Hand Tracker V6", img)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()