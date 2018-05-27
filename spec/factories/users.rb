FactoryBot.define do
  factory :user do
    sequence :full_name do |n|
      "Brewer #{n}"
    end

    email do
      "#{full_name.delete(" ")}@example.com"
    end

    admin false

    trait :deactivated do
      deactivated_at { Time.now }
    end
  end
end
