FactoryBot.define do
  factory :competition do
    url "MyString"
    date "2018-05-28"
    name "MyString"
    competition_type Competition::TYPES.first
  end
end
