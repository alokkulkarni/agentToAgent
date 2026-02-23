# AWS Chime SDK Setup Guide

This guide details how to configure permissions for the AWS Chime SDK, specifically focusing on the `chime.amazonaws.com` service principal in resource-based policies.

## Understanding `chime.amazonaws.com`

The identifier `chime.amazonaws.com` is a **Service Principal**, not an IAM permission action. It represents the AWS Chime service itself. You use this principal in **Resource-based Policies** (like S3 Bucket Policies or SNS Access Policies) to grant the Chime service permission to access your resources on your behalf.

Common use cases include:
- Storing meeting recordings in an S3 bucket.
- Sending notifications to an SNS topic.
- Logging to CloudWatch Logs.

## Validating the Principal

Yes, `chime.amazonaws.com` is the correct service principal for the AWS Chime service.

**Note:** For some specific features like media pipelines or voice connectors, you might also see `mediapipelines.chime.amazonaws.com` or `voiceconnector.chime.amazonaws.com`. However, `chime.amazonaws.com` is the general service principal.

## Step-by-Step: Configuring Resource-Based Policy (S3 Example)

This example shows how to allow AWS Chime to write meeting recordings to your S3 bucket.

### 1. Create an S3 Bucket (if you haven't already)
1. Go to the **Amazon S3** console.
2. Click **Create bucket**.
3. Enter a unique bucket name (e.g., `my-chime-recordings-bucket`).
4. Select your region.
5. Click **Create bucket**.

### 2. Add the Resource Policy
1. In the S3 Console, click on your bucket name.
2. Go to the **Permissions** tab.
3. Scroll down to the **Bucket policy** section and click **Edit**.
4. Paste the following JSON policy, replacing `YOUR_BUCKET_NAME` and `YOUR_AWS_ACCOUNT_ID` with your actual values.

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "AWSChimeReadWrite",
            "Effect": "Allow",
            "Principal": {
                "Service": "chime.amazonaws.com"
            },
            "Action": [
                "s3:PutObject",
                "s3:PutObjectAcl",
                "s3:GetObject",
                "s3:GetObjectAcl"
            ],
            "Resource": [
                "arn:aws:s3:::YOUR_BUCKET_NAME/*"
            ],
            "Condition": {
                "StringEquals": {
                    "aws:SourceAccount": "YOUR_AWS_ACCOUNT_ID"
                }
            }
        }
    ]
}
```

5. Click **Save changes**.

### Key Configuration Details:
- **Principal**: Set to `"Service": "chime.amazonaws.com"`. This tells S3 to trust the Chime service.
- **Action**: `s3:PutObject` allows writing files. `s3:GetObject` allows reading (if needed for playback).
- **Condition**: The `aws:SourceAccount` condition is critical for security. It ensures that only Chime resources from **your** account can access this bucket, preventing the "Confused Deputy" problem.

## Configuring IAM Role for Chime Actions

If your application (e.g., a Lambda function or a backend server) needs to interact with the Chime API (like creating meetings), it needs an IAM Policy attached to its execution role.

### Step-by-Step: Create IAM Policy
1. Go to the **IAM Console**.
2. Click **Policies** -> **Create policy**.
3. Click the **JSON** tab.
4. Paste the following policy:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "chime:CreateMeeting",
                "chime:DeleteMeeting",
                "chime:GetMeeting",
                "chime:ListMeetings",
                "chime:CreateAttendee",
                "chime:BatchCreateAttendee",
                "chime:DeleteAttendee",
                "chime:GetAttendee",
                "chime:ListAttendees"
            ],
            "Resource": "*"
        }
    ]
}
```
5. Click **Next: Tags** (optional) -> **Next: Review**.
6. Name the policy (e.g., `ChimeSDKAccessPolicy`).
7. Click **Create policy**.

### Attach to Role (e.g., for Lambda)
1. Go to **Roles** in IAM Console.
2. Find the role used by your Lambda function or EC2 instance.
3. Click **Add permissions** -> **Attach policies**.
4. Search for `ChimeSDKAccessPolicy`.
5. Select it and click **Add permissions**.

## Troubleshooting

- **"Invalid Principal" Error**: Ensure you entered `chime.amazonaws.com` correctly in the JSON.
- **Access Denied**: Check that the `aws:SourceAccount` condition matches your account ID.
- **Region Issues**: Chime global API endpoint is `us-east-1`, but media regions vary. Ensure your SDK client is configured correctly.
