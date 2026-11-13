# percy-dancing-in-the-dark

Mấy điều mình giữ khi đi làm. Viết ra để tự nhắc, ai thấy hợp thì lấy.

## 1. Làm xong mới tính là làm

Code chạy trên máy mình chưa phải là xong. Xong là đã test trên máy thật, có ảnh, có link MR, và người review đọc là hiểu.

## 2. Hỏi sớm, hỏi rõ

Chưa rõ yêu cầu thì hỏi ngay, đừng đoán rồi làm lại. Mỗi câu hỏi nên trả lời được bằng có hoặc không, kèm ảnh để người ta khỏi phải mở máy.

## 3. Ít mà chắc

Đoạn code ngắn nhất mà đúng là đoạn tốt nhất. Đừng viết sẵn cho "sau này", sau này tự lo.

## 4. Sửa tận gốc

Bug báo ở một chỗ thường nằm ở nhiều chỗ. Tìm hết, sửa một lần.

## 5. Không lén làm thay người khác quyết

Commit, merge, chuyển ticket, nhắn nhóm: luôn hỏi trước. Mô tả quy trình không phải là cho phép.

## 6. Nói thật về kết quả

Test fail thì nói fail. Chưa test được thì ghi rõ chưa test được cái gì.

## 7. Máy cũng cần thở

Đừng chạy mọi thứ cùng lúc. Một việc nặng một lúc, xong thì tắt.

## 8. Nhảy trong bóng tối

Không phải lúc nào cũng có spec, có API, có Figma đủ. Vẫn làm được: mock trước, ghi lại giả định, bật đèn lên thì chỉnh.

## Làm với team

- **Tag đúng người.** PO là người tạo ticket (theo team của chính ticket), BE là người làm ticket API, teamlead nhận review MR.
- **Hỏi trên Jira trước, nhắc trên Chat sau.** Chat chỉ để nhắc người ta vào xem.
- **Đọc hết tài liệu trước khi kết luận.** Ticket, story, ticket API, Confluence, kể cả mục Out of scope.
- **Chỉ nhắc khi cần người ta làm gì đó.** Một tin một ticket.
- **Xong task là có bằng chứng.** Ảnh dark/light, link MR, rồi mới chuyển trạng thái.
- **Không gửi gì ra ngoài khi chưa duyệt.** Mọi comment/tin nhắn đi qua nút ✅ trên Telegram.

## Runner

Repo này public để dùng máy GitHub miễn phí. **Không có thông tin công việc nào nằm trong code hay log**: ticket, nhánh, sheet, tên người, webhook đều là secret hoặc nằm trong repo task private. Log chỉ in số đếm.

| Workflow | Việc |
|---|---|
| `daily` | 09:00 thứ 2–6: điền sheet daily, gửi báo cáo theo squad lên Telegram; mỗi 5 phút đọc ❤️ và nút ✅/❌ |
| `ticket` | nhận **số task** trong repo task private. Job code (Linux): Claude làm tiếp nhánh theo Jira + Figma + test case QC, chạy verify/jest, đẩy lên `runner/<nhánh>`. Job **iOS** (macOS, simulator) và **Android** (Linux, emulator): build staging, chạy test case QC trên Jira, so Figma + requirement ở light/dark/RTL, gửi ảnh + HTML so sánh. Báo cáo vào task + Telegram |
| `retro` | 17:00 thứ 6: thống kê sprint |
| `remind` | gửi tin nhắc vào Chat/Telegram |

Máy Mac (launchd): `ask-bot.py` (hỏi đáp dự án, chỉ đọc), `mac-retro.py` (chi phí AI + bài học).

### Giao việc cho runner
```
scripts/task.sh <nhánh RN> [account 1-3|auto] [model] [ghi chú...]
```
Tạo task trong repo private (tiêu đề = mã Jira + tên ticket), rồi chạy `ticket` với số task. Tài khoản Claude chọn tự động (`pick-account.py`): bỏ qua tài khoản đã dùng ≥ 90% quota tuần mà còn hơn 1 ngày mới reset. Runner luôn làm theo ticket Jira: gom context (`ticket-context.py`) và Figma trước khi code.

### Xong task → Jira (theo cú pháp team)
Ảnh app (light/dark/RTL) và Figma của mỗi task nằm ngay trong comment báo cáo của task (repo private), kèm album trên Telegram.
Khi đã mở MR RN và bấm port Kotlin:
```
scripts/queue-port.sh <số task> <số MR RN> [mã Jira khác dùng chung nhánh]
```
`port-watch.sh` trên Mac (15 phút/lần) quét `uniscore-kotlin`. Khi có MR Android, nó comment lên Jira: ảnh dark | light, `MR RN`, `MR Android`, `cc @Mason`, rồi chuyển REVIEW CODE.

### Cài trên máy mới
1. `gh auth login`
2. Chép các file secret từ repo setup private về đúng chỗ (chmod 600).
3. `scripts/setup.sh` — nạp toàn bộ secret, cài launchd trên Mac.
